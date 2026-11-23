"""Technical validation runs (FR-060): check a processed version against the project's
rules and keep every run; the newest one is the version's report. Informative only
(RULE-009): a failed rule never changes the version's state.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from asset_studio.db import utcnow, uuid7
from asset_studio.errors import DomainError
from asset_studio.modules.assets.models import Asset, AssetVersion
from asset_studio.modules.assets.service import get_asset
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.projects.service import current_config, get_project
from asset_studio.modules.quality.models import ValidationResult
from asset_studio.modules.quality.validation import RULES, Expectations, render_name, validate
from asset_studio.modules.storage.local import LocalStorage

DEFAULT_VIEW = "main"


@dataclass
class Report:
    run_id: uuid.UUID | None
    results: list[ValidationResult]

    @property
    def summary(self) -> dict[str, int]:
        out = {"passed": 0, "failed": 0, "skipped": 0}
        for r in self.results:
            out[r.status] += 1
        return out


def _view(version: AssetVersion) -> str:
    pose = (version.generation_metadata or {}).get("pose") or {}
    view = pose.get("view") if isinstance(pose, dict) else None
    return str(view) if view else DEFAULT_VIEW


def _values(asset: Asset, version: AssetVersion, out: dict[str, Any]) -> dict[str, str]:
    return {
        "asset": asset.slug,
        "category": asset.category,
        "view": _view(version),
        "version": f"v{version.number}",
        "size": f"{out['width']}x{out['height']}",
    }


def run(session: Session, storage: LocalStorage, version: AssetVersion, actor: Actor) -> Report:
    """Validate the processed file of ``version`` and store the results as a new run."""
    out = (version.processing or {}).get("output")
    if not out:
        raise DomainError(409, "VERSION_NOT_PROCESSED", "The version has no processed file yet.")
    asset = get_asset(session, version.asset_id)
    config = current_config(session, get_project(session, asset.project_id))
    try:
        data = storage.path(out["key"]).read_bytes()
    except FileNotFoundError:
        data = b""  # reported by the integrity rule
    values = _values(asset, version, out)

    def file_name(slug: str, category: str) -> str:
        pattern = render_name(config.naming, values | {"asset": slug, "category": category})
        return f"{pattern}.{out['ext']}"

    name = file_name(asset.slug, asset.category)
    # Two assets of the project that would get the same file name collide on export.
    others = session.scalars(
        select(Asset).where(
            Asset.project_id == asset.project_id,
            Asset.id != asset.id,
            Asset.archived_at.is_(None),
        )
    )
    collisions = tuple(o.slug for o in others if file_name(o.slug, o.category) == name)
    results = validate(
        data,
        Expectations(
            width=config.output.width,
            height=config.output.height,
            format=config.output.format,
            background=config.output.background,
            max_file_kb=config.validation.max_file_kb,
            aspect_tolerance=config.validation.aspect_tolerance,
            sha256=out["sha256"],
            file_name=name,
            collisions=collisions,
        ),
    )
    run_id, now = uuid7(), utcnow()
    rows = [
        ValidationResult(
            asset_version_id=version.id,
            run_id=run_id,
            rule=r.rule,
            status=r.status,
            details=r.details,
            created_at=now,
        )
        for r in results
    ]
    session.add_all(rows)
    session.flush()
    report = Report(run_id, rows)
    record(
        session,
        actor=actor,
        action="asset_version.validated",
        subject_type="asset_version",
        subject_id=version.id,
        project_id=asset.project_id,
        data={"run_id": str(run_id), **report.summary},
    )
    return report


def latest(session: Session, version_id: uuid.UUID) -> Report:
    run_id = session.scalar(
        select(ValidationResult.run_id)
        .where(ValidationResult.asset_version_id == version_id)
        .order_by(ValidationResult.run_id.desc())
        .limit(1)
    )
    if run_id is None:
        return Report(None, [])
    rows = session.scalars(select(ValidationResult).where(ValidationResult.run_id == run_id))
    order = {rule: i for i, rule in enumerate(RULES)}
    return Report(run_id, sorted(rows, key=lambda r: order.get(r.rule, len(order))))
