"""System status (NFR-003, Storage-and-Backup) and the dashboard summary (FR-100)."""

import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from asset_studio.config import get_settings
from asset_studio.db import utcnow
from asset_studio.modules.assets.models import Asset, AssetVersion
from asset_studio.modules.assets.service import consistency_report
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.jobs.models import Job
from asset_studio.modules.models.models import Model
from asset_studio.modules.models.service import licence_status
from asset_studio.modules.storage.local import LocalStorage
from asset_studio.modules.system import backup
from asset_studio.modules.system.settings import queue_paused

# Remind the user to back up when the newest backup is older than this (ADR-013).
BACKUP_REMINDER = timedelta(days=7)


def _usage(root: Path) -> dict[str, Any]:
    files, size = 0, 0
    projects = root / "projects"
    if projects.is_dir():
        for p in projects.rglob("*"):
            if p.is_file():
                files += 1
                size += p.stat().st_size
    try:
        disk = shutil.disk_usage(root if root.exists() else root.parent)
        free: int | None = disk.free
        total: int | None = disk.total
    except OSError:
        free = total = None
    return {"files": files, "bytes": size, "free_bytes": free, "total_bytes": total}


def last_backup() -> dict[str, Any] | None:
    readable = [b for b in backup.list_backups() if b.get("readable")]
    return readable[0] if readable else None


def backup_due(newest: dict[str, Any] | None) -> bool:
    if newest is None or not newest.get("created_at"):
        return True
    return utcnow() - datetime.fromisoformat(newest["created_at"]) > BACKUP_REMINDER


def status(session: Session, storage: LocalStorage) -> dict[str, Any]:
    """Everything the System status screen shows, without host paths (ADR-013)."""
    settings = get_settings()
    conn = session.connection()
    folder = backup.backups_dir()
    newest = last_backup()
    report = consistency_report(session, storage)
    queue = jobs.summary(session)
    return {
        "database": {
            "ok": True,
            "schema_revision": backup.schema_revision(conn),
            "head_revision": backup.head_revision(),
        },
        "queue": {**queue, "paused": queue_paused(session)},
        "storage": {
            "volume": "asset-data",
            **_usage(storage.root),
            "empty": backup.data_location_empty(conn, storage.root),
        },
        "consistency": {
            "missing": len(report["missing"]),
            "orphans": len(report["orphans"]),
            "missing_versions": report["missing"][:20],
        },
        "backups": {
            "configured": folder.is_dir(),
            "last": newest,
            "due": backup_due(newest),
        },
        "locations": {
            "export_roots": len(settings.export_roots),
            "models_folder": bool(settings.models_dir) and Path(settings.models_dir).is_dir(),
            "engine_url": settings.comfyui_url,
        },
        "mcp": {"configured": bool(settings.mcp_token), "port": settings.mcp_port},
    }


def dashboard(session: Session, project_id: uuid.UUID) -> dict[str, Any]:
    """The attention cards, versions by state, latest versions and failures (FR-100)."""
    live = (Asset.project_id == project_id, Asset.archived_at.is_(None))
    by_state = {
        state: n
        for state, n in session.execute(
            select(AssetVersion.state, func.count())
            .join(Asset, Asset.id == AssetVersion.asset_id)
            .where(*live, AssetVersion.deleted_at.is_(None))
            .group_by(AssetVersion.state)
        )
    }
    latest = [
        {
            "id": v.id,
            "asset_id": a.id,
            "asset_name": a.name,
            "category": a.category,
            "number": v.number,
            "state": v.state,
            "created_at": v.created_at,
        }
        for v, a in session.execute(
            select(AssetVersion, Asset)
            .join(Asset, Asset.id == AssetVersion.asset_id)
            .where(*live, AssetVersion.deleted_at.is_(None))
            .order_by(AssetVersion.id.desc())
            .limit(8)
        )
    ]
    since = utcnow() - timedelta(days=7)
    failed = (Job.project_id == project_id, Job.state == "failed", Job.finished_at >= since)
    failed_jobs = [
        {
            "id": j.id,
            "kind": j.kind,
            "finished_at": j.finished_at,
            "code": (j.error or {}).get("code"),
            "message": (j.error or {}).get("message"),
        }
        for j in session.scalars(select(Job).where(*failed).order_by(Job.id.desc()).limit(5))
    ]
    installed = list(session.scalars(select(Model).where(Model.status == "installed")))
    licences = licence_status(session, project_id, installed)
    newest = last_backup()
    return {
        "versions_by_state": by_state,
        "attention": {
            "awaiting_review": by_state.get("awaiting_review", 0),
            "processing_failed": by_state.get("processing_failed", 0),
            "failed_jobs": session.scalar(select(func.count()).where(*failed)) or 0,
            "licence_warnings": sum(
                1 for s in licences.values() if s.conflict and not s.acknowledged
            ),
            "backup_due": backup_due(newest),
        },
        "latest_versions": latest,
        "failed_jobs": failed_jobs,
        "last_backup": newest,
    }
