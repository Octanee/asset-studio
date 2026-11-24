"""SVG generation (FR-045, FR-046, UC-014): preview, queueing and the CPU job.

A request names the project, the target asset, a template and its parameters, and
optionally a style whose palette the colours must come from. ``render`` is pure and quick,
so the SVG Studio previews every change with the real output. ``queue`` puts one CPU job
in the queue; the job renders again (same template version, same parameters, same file),
stores the cleaned SVG as a new version and starts the usual processing and review.
"""

import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from asset_studio.errors import DomainError
from asset_studio.modules.assets import service as assets
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.jobs.models import Job
from asset_studio.modules.jobs.runner import JobContext
from asset_studio.modules.processing import service as processing
from asset_studio.modules.projects.service import get_project
from asset_studio.modules.storage.local import get_storage
from asset_studio.modules.styles.service import get_style
from asset_studio.modules.svg.raster import SVG_MIME
from asset_studio.modules.svg.sanitize import Clean, SvgError, clean
from asset_studio.modules.svg.templates import Template, get_template, normalise

# Neutrals a palette never has to list: white and black glyphs on coloured shapes.
NEUTRALS = frozenset({"#ffffff", "#000000"})


class AssetTarget(BaseModel):
    """An existing asset (a new version of it) or a new asset in a category."""

    model_config = ConfigDict(extra="forbid")
    asset_id: uuid.UUID | None = None
    category: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)


class SvgSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID
    asset: AssetTarget | None = None  # not needed for a preview
    template_id: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    style_id: uuid.UUID | None = None


@dataclass
class Rendered:
    template: Template
    params: dict[str, Any]
    params_hash: str
    clean: Clean
    style: dict[str, Any] | None
    problems: list[dict[str, str]]

    @property
    def data(self) -> bytes:
        return self.clean.svg.encode()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def params_hash(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def render(session: Session, spec: SvgSpec) -> Rendered:
    get_project(session, spec.project_id)
    template = get_template(spec.template_id)
    params = normalise(template, spec.params)
    try:
        cleaned = clean(template.draw(params))
    except SvgError as exc:  # a template bug, never the user's input
        raise DomainError(500, exc.code, str(exc)) from exc
    problems: list[dict[str, str]] = []
    style = None
    if spec.style_id is not None:
        row = get_style(session, spec.style_id)
        if row.project_id != spec.project_id:
            raise DomainError(422, "STYLE_OTHER_PROJECT", "The style belongs to another project.")
        palette = sorted({str(c).lower() for c in (row.attributes or {}).get("palette", [])})
        style = {"id": str(row.id), "version": row.version, "palette": palette}
        if palette:
            allowed = set(palette) | NEUTRALS
            problems += [
                {
                    "code": "PALETTE_MISMATCH",
                    "param": p.name,
                    "detail": f"{params[p.name]} is not in the style's palette.",
                }
                for p in template.params
                if p.kind == "color" and params[p.name] not in allowed
            ]
    return Rendered(template, params, params_hash(params), cleaned, style, problems)


def metadata(r: Rendered, job_id: uuid.UUID | None = None) -> dict[str, Any]:
    """What made the version (RULE-011): enough to make the same file again."""
    return {
        "engine": {"name": "svg", "version": None},
        "template": {"id": r.template.id, "version": r.template.version},
        "params": r.params,
        "params_hash": r.params_hash,
        "style": {"id": r.style["id"], "version": r.style["version"]} if r.style else None,
        "svg": r.clean.report,
        "job_id": str(job_id) if job_id else None,
    }


@dataclass
class Queued:
    asset_id: uuid.UUID
    job: Job


def queue(session: Session, spec: SvgSpec, actor: Actor) -> Queued:
    if actor not in ("user", "mcp"):
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "SVG is requested by the user or Claude.")
    target = spec.asset
    if target is None or (target.asset_id is None) == (target.category is None):
        raise DomainError(
            422, "SVG_TARGET_REQUIRED", "Give either asset.asset_id or asset.category and name."
        )
    r = render(session, spec)
    if r.problems:
        raise DomainError(
            422, "SVG_NOT_READY", "Fix these problems first.", {"problems": r.problems}
        )
    if target.asset_id is not None:
        asset = assets.get_asset(session, target.asset_id)
        if asset.project_id != spec.project_id:
            raise DomainError(422, "ASSET_OTHER_PROJECT", "The asset belongs to another project.")
    else:
        asset = assets.create_asset(
            session,
            spec.project_id,
            category=target.category or "",
            name=target.name or r.template.name,
            actor="user" if actor == "user" else "system",
        )
    frozen = spec.model_copy(update={"asset": AssetTarget(asset_id=asset.id), "params": r.params})
    job = jobs.enqueue(
        session,
        "svg",
        {
            "spec": frozen.model_dump(mode="json"),
            "template": {"id": r.template.id, "version": r.template.version},
            "sha256": r.sha256,
        },
        actor=actor,
        project_id=spec.project_id,
    )
    record(
        session,
        actor=actor,
        action="svg.queued",
        subject_type="asset",
        subject_id=asset.id,
        project_id=spec.project_id,
        data={
            "template": {"id": r.template.id, "version": r.template.version},
            "params_hash": r.params_hash,
            "job_id": str(job.id),
        },
    )
    return Queued(asset.id, job)


def handle_svg(ctx: JobContext) -> dict[str, Any]:
    storage = get_storage()
    spec = SvgSpec.model_validate(ctx.params["spec"])
    if spec.asset is None or spec.asset.asset_id is None:
        raise DomainError(422, "SVG_TARGET_REQUIRED", "The job has no target asset.")
    asset_id = spec.asset.asset_id
    with ctx.runner.sessions() as s, s.begin():
        r = render(s, spec)
        wanted = ctx.params.get("template") or {}
        if wanted.get("version") != r.template.version:
            raise DomainError(
                409,
                "SVG_TEMPLATE_CHANGED",
                "The template changed after this job was queued; queue it again.",
                {"queued": wanted, "now": r.template.version},
            )
        version = assets.add_version(
            s,
            storage,
            asset_id,
            io.BytesIO(r.data),
            mime=SVG_MIME,
            actor="system",
            width=round(r.clean.width),
            height=round(r.clean.height),
            generation_job_id=ctx.job_id,
            generation_metadata=metadata(r, ctx.job_id),
        )
        processing.start(s, version.id, "system")  # thumbnails, validation, review
        return {"asset_id": str(asset_id), "versions": [str(version.id)], "sha256": r.sha256}


HANDLERS = {"svg": handle_svg}
