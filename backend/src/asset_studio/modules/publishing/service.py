"""Publishing (FR-090 to FR-095, Publishing workflow, D-28).

Publishing = writing an approved version to a target through a preset. It runs in three steps:

1. **Plan** (``plan``): the versions to publish and every file they would write, with the
   files that already exist in the target (DD-006).
2. **Publish** (``publish``): the user confirms each overwrite by path (RULE-004); existing
   files are checked again at this moment. MCP may publish only where the project allows it,
   and never overwrites (RULE-005, MCP-Architecture). The work is an ``export`` job.
3. **Export job** (``handle_export``): renders and writes the files, records a publication
   with each file's hash, moves the version to ``published`` (T-09, or T-10 when published
   again) and points the asset's current publication in that target at it (FR-093).
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from asset_studio.db import utcnow
from asset_studio.errors import DomainError
from asset_studio.modules.assets import service as assets
from asset_studio.modules.assets.models import Asset, AssetVersion, CollectionItem
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.jobs.models import Job
from asset_studio.modules.jobs.runner import Handler, JobContext
from asset_studio.modules.processing import imaging
from asset_studio.modules.projects.models import Project
from asset_studio.modules.projects.service import current_config, get_project
from asset_studio.modules.publishing import files
from asset_studio.modules.publishing.models import (
    CurrentPublication,
    ExportPreset,
    ExportTarget,
    Publication,
    PublicationFile,
    PublicationPlan,
)
from asset_studio.modules.publishing.presets import PresetDefinition, file_paths
from asset_studio.modules.storage.local import LocalStorage, get_storage
from asset_studio.modules.svg import raster
from asset_studio.modules.svg.sanitize import SvgError, clean

PUBLISHABLE = ("approved", "published")
PLAN_TTL = timedelta(hours=1)
MAX_VERSIONS = 2000


def _user(actor: Actor, what: str) -> None:
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", f"Only the user can change {what}.")


def _name(name: str) -> str:
    name = " ".join(name.split())[:120]
    if not name:
        raise DomainError(422, "NAME_REQUIRED", "A name is required.")
    return name


def _unique(
    session: Session,
    model: type[ExportPreset] | type[ExportTarget],
    project_id: uuid.UUID,
    name: str,
    own: uuid.UUID | None,
) -> None:
    clash = session.scalar(
        select(model.id).where(model.project_id == project_id, model.name == name)
    )
    if clash is not None and clash != own:
        raise DomainError(409, "NAME_TAKEN", "This name is already used in the project.")


# --- presets (FR-090) -------------------------------------------------------------------------


def get_preset(session: Session, preset_id: uuid.UUID) -> ExportPreset:
    preset = session.get(ExportPreset, preset_id)
    if preset is None:
        raise DomainError(404, "PRESET_NOT_FOUND", "Export preset not found.")
    return preset


def list_presets(
    session: Session, project_id: uuid.UUID, archived: bool = False
) -> list[ExportPreset]:
    get_project(session, project_id)
    q = (
        select(ExportPreset)
        .where(ExportPreset.project_id == project_id)
        .order_by(ExportPreset.name)
    )
    if not archived:
        q = q.where(ExportPreset.archived_at.is_(None))
    return list(session.scalars(q))


def save_preset(
    session: Session,
    *,
    name: str,
    definition: PresetDefinition,
    actor: Actor,
    project_id: uuid.UUID | None = None,
    preset_id: uuid.UUID | None = None,
) -> ExportPreset:
    """Create a preset (``project_id``) or change one (``preset_id``). Publications keep the
    preset id; the files they wrote are recorded with their hashes."""
    _user(actor, "export presets")
    name = _name(name)
    data = definition.model_dump()
    if preset_id is None:
        if project_id is None:
            raise DomainError(422, "PROJECT_REQUIRED", "A project is required.")
        get_project(session, project_id)
        _unique(session, ExportPreset, project_id, name, None)
        preset = ExportPreset(project_id=project_id, name=name, definition=data)
        session.add(preset)
        action = "export_preset.created"
    else:
        preset = get_preset(session, preset_id)
        _unique(session, ExportPreset, preset.project_id, name, preset.id)
        preset.name, preset.definition = name, data
        action = "export_preset.changed"
    session.flush()
    record(
        session,
        actor=actor,
        action=action,
        subject_type="export_preset",
        subject_id=preset.id,
        project_id=preset.project_id,
        data={"name": name, "definition": data},
    )
    return preset


def archive_preset(
    session: Session, preset_id: uuid.UUID, archived: bool, actor: Actor
) -> ExportPreset:
    _user(actor, "export presets")
    preset = get_preset(session, preset_id)
    if (preset.archived_at is not None) != archived:
        preset.archived_at = utcnow() if archived else None
        record(
            session,
            actor=actor,
            action="export_preset.archived" if archived else "export_preset.restored",
            subject_type="export_preset",
            subject_id=preset.id,
            project_id=preset.project_id,
        )
    return preset


# --- targets (FR-091) -------------------------------------------------------------------------


def get_target(session: Session, target_id: uuid.UUID) -> ExportTarget:
    target = session.get(ExportTarget, target_id)
    if target is None:
        raise DomainError(404, "TARGET_NOT_FOUND", "Export target not found.")
    return target


def list_targets(
    session: Session, project_id: uuid.UUID, archived: bool = False
) -> list[ExportTarget]:
    get_project(session, project_id)
    q = (
        select(ExportTarget)
        .where(ExportTarget.project_id == project_id)
        .order_by(ExportTarget.name)
    )
    if not archived:
        q = q.where(ExportTarget.archived_at.is_(None))
    return list(session.scalars(q))


def create_target(
    session: Session, project_id: uuid.UUID, name: str, root_id: str, subdir: str, actor: Actor
) -> ExportTarget:
    """A folder under a configured export root; it is created on the first publish."""
    _user(actor, "export targets")
    get_project(session, project_id)
    name = _name(name)
    root = next((r for r in files.roots() if r.id == root_id), None)
    if root is None:
        raise DomainError(
            422, "EXPORT_ROOT_UNKNOWN", "Choose one of the configured export folders."
        )
    sub = files.clean_subdir(subdir)
    files.inside(root.path, sub)
    _unique(session, ExportTarget, project_id, name, None)
    target = ExportTarget(project_id=project_id, name=name, root=str(root.path), subdir=sub)
    session.add(target)
    session.flush()
    record(
        session,
        actor=actor,
        action="export_target.created",
        subject_type="export_target",
        subject_id=target.id,
        project_id=project_id,
        data={"name": name, "root": root.name, "subdir": sub},
    )
    return target


def archive_target(
    session: Session, target_id: uuid.UUID, archived: bool, actor: Actor
) -> ExportTarget:
    _user(actor, "export targets")
    target = get_target(session, target_id)
    if (target.archived_at is not None) != archived:
        target.archived_at = utcnow() if archived else None
        record(
            session,
            actor=actor,
            action="export_target.archived" if archived else "export_target.restored",
            subject_type="export_target",
            subject_id=target.id,
            project_id=target.project_id,
        )
    return target


def root_name(target: ExportTarget) -> str | None:
    """The configured root's name, or None when the root is not configured any more."""
    return next((r.name for r in files.roots() if str(r.path) == target.root), None)


# --- plan (DD-006, RULE-004) ------------------------------------------------------------------


def _may_publish(project: Project, actor: Actor) -> None:
    if actor == "mcp" and not project.mcp_can_decide:
        raise DomainError(403, "MCP_NOT_ALLOWED", "This project does not allow Claude to publish.")
    if actor not in ("user", "mcp"):
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Publishing is started by the user or Claude.")


def _view(version: AssetVersion) -> str:
    pose = (version.generation_metadata or {}).get("pose") or {}
    return str(pose.get("view") or "main") if isinstance(pose, dict) else "main"


def _values(project: Project, asset: Asset, version: AssetVersion) -> dict[str, str]:
    return {
        "project": project.slug,
        "asset": asset.slug,
        "category": asset.category,
        "view": _view(version),
        "version": f"v{version.number}",
    }


def _skip(v: AssetVersion, a: Asset, reason: str) -> dict[str, Any]:
    return {
        "version_id": str(v.id),
        "asset": a.name,
        "number": v.number,
        "state": v.state,
        "reason": reason,
    }


def _candidates(
    session: Session,
    project_id: uuid.UUID,
    version_ids: list[uuid.UUID] | None,
    collection_id: uuid.UUID | None,
) -> tuple[list[tuple[AssetVersion, Asset]], list[dict[str, Any]]]:
    """The versions to publish and the ones left out, with the reason (FR-092).

    Chosen versions are taken as they are. For a collection or the whole project, each
    asset contributes its newest approved or published version."""
    skipped: list[dict[str, Any]] = []
    if version_ids:
        rows = [
            (v, a)
            for v, a in session.execute(
                select(AssetVersion, Asset)
                .join(Asset, Asset.id == AssetVersion.asset_id)
                .where(AssetVersion.id.in_(version_ids))
                .order_by(Asset.slug, AssetVersion.number)
            )
        ]
        found = {v.id for v, _ in rows}
        missing = [str(i) for i in version_ids if i not in found]
        if missing:
            raise DomainError(
                404, "VERSION_NOT_FOUND", "Version not found.", {"version_ids": missing}
            )
        if any(a.project_id != project_id for _, a in rows):
            raise DomainError(422, "VERSION_OTHER_PROJECT", "A version belongs to another project.")
        chosen = []
        for v, a in rows:
            if v.state in PUBLISHABLE:
                chosen.append((v, a))
            else:
                skipped.append(_skip(v, a, "NOT_APPROVED"))
        return chosen, skipped

    q = (
        select(AssetVersion, Asset)
        .join(Asset, Asset.id == AssetVersion.asset_id)
        .where(Asset.project_id == project_id, Asset.archived_at.is_(None))
        .order_by(Asset.slug, AssetVersion.number.desc())
    )
    if collection_id:
        q = q.where(
            Asset.id.in_(
                select(CollectionItem.asset_id).where(CollectionItem.collection_id == collection_id)
            )
        )
    best: dict[uuid.UUID, tuple[AssetVersion, Asset]] = {}
    seen: dict[uuid.UUID, Asset] = {}
    for v, a in session.execute(q):
        seen[a.id] = a
        if a.id not in best and v.state in PUBLISHABLE:
            best[a.id] = (v, a)
    for asset_id, a in seen.items():
        if asset_id not in best:
            skipped.append(
                {"asset": a.name, "asset_id": str(a.id), "reason": "NO_APPROVED_VERSION"}
            )
    return list(best.values()), skipped


@dataclass
class PlanView:
    plan: PublicationPlan
    preset: ExportPreset
    target: ExportTarget

    @property
    def overwrites(self) -> list[str]:
        return [f["path"] for i in self.plan.items for f in i["files"] if f["exists"]]

    @property
    def file_count(self) -> int:
        return sum(len(i["files"]) for i in self.plan.items)


def _sidecar(path: str) -> str:
    return path.rsplit(".", 1)[0] + ".json"


def plan(
    session: Session,
    project_id: uuid.UUID,
    *,
    preset_id: uuid.UUID,
    target_id: uuid.UUID,
    actor: Actor,
    version_ids: list[uuid.UUID] | None = None,
    collection_id: uuid.UUID | None = None,
) -> PlanView:
    """Every file a publish would write, and which of them already exist (DD-006)."""
    project = get_project(session, project_id)
    _may_publish(project, actor)
    preset, target = get_preset(session, preset_id), get_target(session, target_id)
    if preset.project_id != project_id or target.project_id != project_id:
        raise DomainError(
            422, "OTHER_PROJECT", "The preset and the target must belong to the project."
        )
    if preset.archived_at or target.archived_at:
        raise DomainError(409, "ARCHIVED", "The preset or the target is archived.")
    definition = PresetDefinition.model_validate(preset.definition)
    base = files.target_dir(target.root, target.subdir)
    versions, skipped = _candidates(session, project_id, version_ids, collection_id)
    if len(versions) > MAX_VERSIONS:
        raise DomainError(
            422, "PLAN_TOO_LARGE", f"Publish at most {MAX_VERSIONS} versions at once."
        )

    items: list[dict[str, Any]] = []
    owner: dict[str, str] = {}
    for v, a in versions:
        if actor == "mcp" and v.state == "published":
            skipped.append(_skip(v, a, "REPUBLISH_USER_ONLY"))  # T-10 is the user's call
            continue
        if definition.format == "svg" and not raster.is_svg(_source_mime(v)):
            skipped.append(_skip(v, a, "NOT_VECTOR"))  # a raster cannot become a vector
            continue
        paths = [p for _, p in file_paths(definition, _values(project, a, v))]
        if definition.metadata == "sidecar":
            paths += [_sidecar(p) for p in paths]
        planned = []
        for path in paths:
            if path in owner:
                raise DomainError(
                    409,
                    "PLAN_PATH_COLLISION",
                    "Two versions would write the same file. Change the naming or the choice.",
                    {"path": path, "assets": [owner[path], a.name]},
                )
            owner[path] = a.name
            existing = files.sha256_of(files.inside(base, path))
            planned.append(
                {"path": path, "exists": existing is not None, "existing_sha256": existing}
            )
        items.append(
            {
                "version_id": str(v.id),
                "asset_id": str(a.id),
                "asset": a.name,
                "number": v.number,
                "state": v.state,
                "files": planned,
            }
        )
    if not items:
        raise DomainError(
            409, "NOTHING_TO_PUBLISH", "No approved version to publish.", {"skipped": skipped}
        )
    row = PublicationPlan(
        project_id=project_id,
        preset_id=preset.id,
        target_id=target.id,
        actor=actor,
        items=items,
        skipped=skipped,
    )
    session.add(row)
    session.flush()
    return PlanView(row, preset, target)


def get_plan(session: Session, plan_id: uuid.UUID) -> PlanView:
    row = session.get(PublicationPlan, plan_id)
    if row is None:
        raise DomainError(404, "PLAN_NOT_FOUND", "Publication plan not found.")
    return PlanView(row, get_preset(session, row.preset_id), get_target(session, row.target_id))


# --- publish (RULE-004, RULE-005) -------------------------------------------------------------


def publish(session: Session, plan_id: uuid.UUID, confirmed: list[str], actor: Actor) -> Job:
    """Start the export job for a plan; every existing file must be confirmed by its path."""
    view = get_plan(session, plan_id)
    row = view.plan
    project = get_project(session, row.project_id)
    _may_publish(project, actor)
    if actor != row.actor:
        raise DomainError(403, "PLAN_OTHER_ACTOR", "The plan was made by another actor.")
    if row.used_at is not None:
        raise DomainError(409, "PLAN_USED", "This plan was already published. Plan again.")
    if utcnow() - row.created_at > PLAN_TTL:
        raise DomainError(409, "PLAN_EXPIRED", "The plan is too old. Plan again.")
    base = files.target_dir(view.target.root, view.target.subdir)
    # The target may have changed since planning: look again now.
    existing = [
        f["path"]
        for item in row.items
        for f in item["files"]
        if files.inside(base, f["path"]).is_file()
    ]
    if existing and actor == "mcp":
        raise DomainError(
            403,
            "MCP_OVERWRITE_NOT_ALLOWED",
            "Claude never overwrites files; the user has to publish this.",
            {"paths": existing[:50]},
        )
    missing = sorted(set(existing) - set(confirmed))
    if missing:
        raise DomainError(
            409,
            "OVERWRITE_NOT_CONFIRMED",
            "Some files already exist in the target. Confirm each overwrite.",
            {"paths": missing[:200], "count": len(missing)},
        )
    job = jobs.enqueue(
        session,
        "export",
        {"plan_id": str(row.id), "actor": actor, "confirmed": sorted(existing)},
        actor=actor,
        project_id=row.project_id,
    )
    row.used_at, row.job_id = utcnow(), job.id
    record(
        session,
        actor=actor,
        action="publication.requested",
        subject_type="publication_plan",
        subject_id=row.id,
        project_id=row.project_id,
        data={
            "job_id": str(job.id),
            "versions": len(row.items),
            "files": view.file_count,
            "overwrites_confirmed": len(existing),
            "target": view.target.name,
            "preset": view.preset.name,
        },
    )
    return job


# --- the export job ---------------------------------------------------------------------------


def _source_mime(version: AssetVersion) -> str:
    out = (version.processing or {}).get("output")
    return str(out["mime"]) if out else version.mime


def _source(storage: LocalStorage, version: AssetVersion) -> bytes:
    """The processed file (FR-065), or the original when the version was not processed."""
    out = (version.processing or {}).get("output")
    key = out["key"] if out else version.storage_key
    if key is None:
        raise DomainError(410, "VERSION_DELETED", "The version file was deleted.")
    return storage.path(key).read_bytes()


def _metadata(project: Project, asset: Asset, version: AssetVersion) -> dict[str, Any]:
    """What a sidecar tells the consumer about the file (no paths, no machine data)."""
    meta = version.generation_metadata or {}
    models = meta.get("models") or {}
    return {
        "project": project.slug,
        "asset": asset.slug,
        "name": asset.name,
        "category": asset.category,
        "version": version.number,
        "version_id": str(version.id),
        "source_sha256": version.sha256,
        "prompt": meta.get("prompt"),
        "seed": meta.get("seed"),
        "models": sorted(
            str(m.get("id")) for m in models.values() if isinstance(m, dict) and m.get("id")
        ),
    }


Background = Literal["any", "white", "transparent"]


def _render(
    data: bytes,
    d: PresetDefinition,
    background: Background,
    paths: list[str],
    meta: dict[str, Any],
    *,
    vector: bool = False,
) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    images = paths[: len(d.sizes)]
    for size, path in zip(d.sizes, images, strict=True):
        if d.format == "svg":
            out[path] = clean(data).svg.encode()  # the vector as it is, cleaned again
            continue
        # FR-047: a vector is rendered at this size first, then finished like any image.
        source = raster.render(data, size.width, size.height) if vector else data
        result = imaging.process(
            source,
            imaging.Target(
                width=size.width,
                height=size.height,
                format=d.format,
                background="white" if d.background == "white" else background,
                resize=d.resize,
                optimize=d.optimize,
                quality=d.quality,
            ),
        )
        out[path] = result.data
    if d.metadata == "sidecar":
        for path in images:
            body = {**meta, "file": path.rsplit("/", 1)[-1]}
            out[_sidecar(path)] = (json.dumps(body, indent=2, ensure_ascii=False) + "\n").encode()
    return out


def _publish_one(
    ctx: JobContext,
    storage: LocalStorage,
    plan_row: dict[str, str],
    item: dict[str, Any],
    confirmed: set[str],
) -> dict[str, Any]:
    actor = cast(Actor, ctx.params["actor"])
    version_id = uuid.UUID(item["version_id"])
    target_id, preset_id = uuid.UUID(plan_row["target_id"]), uuid.UUID(plan_row["preset_id"])
    with ctx.runner.sessions() as s:
        version = assets.get_version(s, version_id)
        if version.state not in PUBLISHABLE:
            raise DomainError(409, "NOT_APPROVED", f"The version is {version.state}.")
        asset = assets.get_asset(s, version.asset_id)
        project = get_project(s, asset.project_id)
        target, preset = get_target(s, target_id), get_preset(s, preset_id)
        definition = PresetDefinition.model_validate(preset.definition)
        background = current_config(s, project).output.background
        meta = _metadata(project, asset, version)
        data = _source(storage, version)
        vector = raster.is_svg(_source_mime(version))
        base = files.target_dir(target.root, target.subdir)
    paths = [f["path"] for f in item["files"]]
    if definition.format == "svg" and not vector:
        raise DomainError(409, "NOT_VECTOR", "An SVG preset publishes vector versions only.")
    try:
        rendered = _render(data, definition, background, paths, meta, vector=vector)
    except (imaging.ProcessingError, SvgError) as exc:
        raise DomainError(422, exc.code, str(exc)) from exc
    ctx.check()
    # Never overwrite what the user did not confirm, even a file that appeared after planning.
    surprise = [p for p in rendered if files.inside(base, p).is_file() and p not in confirmed]
    if surprise:
        raise DomainError(
            409,
            "OVERWRITE_NOT_CONFIRMED",
            "A file appeared in the target after planning.",
            {"paths": surprise},
        )
    written = []
    for path, content in rendered.items():
        before = files.sha256_of(files.inside(base, path))
        files.write(base, path, content)
        written.append((path, content, before))

    with ctx.runner.sessions() as s, s.begin():
        version = assets.get_version(s, version_id)
        asset = assets.get_asset(s, version.asset_id)
        publication = Publication(
            asset_version_id=version.id,
            target_id=target_id,
            preset_id=preset_id,
            plan_id=uuid.UUID(plan_row["id"]),
            job_id=ctx.job_id,
            actor=actor,
        )
        s.add(publication)
        s.flush()
        for path, content, before in written:
            s.add(
                PublicationFile(
                    publication_id=publication.id,
                    relative_path=path,
                    sha256=hashlib.sha256(content).hexdigest(),
                    bytes=len(content),
                    overwrote_sha256=before,
                    confirmed_overwrite=before is not None,
                )
            )
            if before is not None:  # AC-003: every overwrite leaves an audit entry
                record(
                    s,
                    actor=actor,
                    action="publication.file_overwritten",
                    subject_type="asset_version",
                    subject_id=version.id,
                    project_id=asset.project_id,
                    data={
                        "path": path,
                        "previous_sha256": before,
                        "publication_id": str(publication.id),
                    },
                )
        action = "publish" if version.state == "approved" else "republish"
        assets.transition(
            s, version.id, action, actor, data={"publication_id": str(publication.id)}
        )
        now = utcnow()
        s.execute(
            insert(CurrentPublication)
            .values(
                asset_id=asset.id,
                target_id=target_id,
                publication_id=publication.id,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["asset_id", "target_id"],
                set_={"publication_id": publication.id, "updated_at": now},
            )
        )
        record(
            s,
            actor=actor,
            action="publication.created",
            subject_type="asset_version",
            subject_id=version.id,
            project_id=asset.project_id,
            data={
                "publication_id": str(publication.id),
                "target_id": str(target_id),
                "preset_id": str(preset_id),
                "files": [p for p, _, _ in written],
                "overwritten": sum(1 for *_, before in written if before is not None),
            },
        )
        return {
            "version_id": item["version_id"],
            "publication_id": str(publication.id),
            "files": len(written),
        }


def handle_export(ctx: JobContext) -> dict[str, Any]:
    """Publish each planned version; one failing version does not stop the others."""
    storage = get_storage()
    with ctx.runner.sessions() as s:
        row = s.get(PublicationPlan, uuid.UUID(ctx.params["plan_id"]))
        if row is None:
            raise DomainError(404, "PLAN_NOT_FOUND", "Publication plan not found.")
        plan_row = {
            "id": str(row.id),
            "target_id": str(row.target_id),
            "preset_id": str(row.preset_id),
        }
        items = list(row.items)
    confirmed = set(ctx.params.get("confirmed") or [])
    published, failed = [], []
    for i, item in enumerate(items):
        ctx.check()
        ctx.progress(step=i, of=len(items), state="publishing")
        try:
            published.append(_publish_one(ctx, storage, plan_row, item, confirmed))
        except DomainError as exc:
            failed.append(
                {
                    "version_id": item["version_id"],
                    "asset": item["asset"],
                    "code": exc.code,
                    "message": str(exc)[:300],
                }
            )
    ctx.progress(step=len(items), of=len(items), state="done")
    if failed and not published:
        raise DomainError(409, failed[0]["code"], "Nothing was published.", {"failed": failed})
    return {
        "published": published,
        "failed": failed,
        "versions": [p["version_id"] for p in published],
    }


HANDLERS: dict[str, Handler] = {"export": handle_export}


# --- reading ----------------------------------------------------------------------------------


def list_publications(
    session: Session,
    *,
    project_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[tuple[Publication, list[PublicationFile]]]:
    q = (
        select(Publication)
        .join(AssetVersion, AssetVersion.id == Publication.asset_version_id)
        .join(Asset, Asset.id == AssetVersion.asset_id)
        .order_by(Publication.id.desc())
        .limit(limit)
    )
    if project_id:
        q = q.where(Asset.project_id == project_id)
    if asset_id:
        q = q.where(Asset.id == asset_id)
    if version_id:
        q = q.where(Publication.asset_version_id == version_id)
    rows = list(session.scalars(q))
    by_pub: dict[uuid.UUID, list[PublicationFile]] = {p.id: [] for p in rows}
    if rows:
        for f in session.scalars(
            select(PublicationFile)
            .where(PublicationFile.publication_id.in_(by_pub.keys()))
            .order_by(PublicationFile.relative_path)
        ):
            by_pub[f.publication_id].append(f)
    return [(p, by_pub[p.id]) for p in rows]


def current_for_asset(session: Session, asset_id: uuid.UUID) -> list[Publication]:
    """The publication each target currently holds for the asset (FR-093)."""
    q = (
        select(Publication)
        .join(CurrentPublication, CurrentPublication.publication_id == Publication.id)
        .where(CurrentPublication.asset_id == asset_id)
        .order_by(Publication.id.desc())
    )
    return list(session.scalars(q))
