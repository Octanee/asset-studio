"""Job handlers for backup and restore (CPU lane; they run even while the queue is paused)."""

from typing import Any

from asset_studio.errors import DomainError
from asset_studio.modules.assets.service import consistency_report
from asset_studio.modules.audit.service import record
from asset_studio.modules.jobs.runner import Handler, JobContext
from asset_studio.modules.storage.local import get_storage
from asset_studio.modules.system import backup


def _actor(ctx: JobContext) -> Any:
    return ctx.params.get("actor", "user")


def handle_backup(ctx: JobContext) -> dict[str, Any]:
    storage = get_storage()
    with ctx.runner.sessions() as s:
        # One snapshot for every table: rows that reference each other stay consistent.
        conn = s.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        result = backup.create_backup(
            conn, storage.root, backup.backups_dir(), progress=ctx.progress
        )
    with ctx.runner.sessions() as s, s.begin():
        record(
            s,
            actor=_actor(ctx),
            action="backup.created",
            subject_type="backup",
            data={k: result[k] for k in ("name", "bytes", "schema_revision", "totals")},
        )
    return result


def handle_restore(ctx: JobContext) -> dict[str, Any]:
    storage = get_storage()
    path = backup.backup_path(str(ctx.params["name"]))
    with ctx.runner.sessions() as s:
        staged = backup.restore_backup(s.connection(), storage.root, path, progress=ctx.progress)
        try:
            record(
                s,
                actor=_actor(ctx),
                action="backup.restored",
                subject_type="backup",
                data={
                    "name": path.name,
                    "schema_revision": staged.manifest["schema_revision"],
                    "rows": sum(staged.rows.values()),
                    "files": len(staged.keys),
                    "cancelled_jobs": staged.cancelled_jobs,
                },
            )
            s.commit()
        except BaseException:
            backup.discard(staged)
            raise
    placed = backup.place_files(staged, storage.root)
    with ctx.runner.sessions() as s:
        report = consistency_report(s, storage)
    if report["missing"]:
        raise DomainError(
            500,
            "RESTORE_INCOMPLETE",
            f"Restored, but {len(report['missing'])} version files are missing.",
            {"missing": report["missing"][:20]},
        )
    return {
        "name": path.name,
        "rows": staged.rows,
        "files": placed,
        "cancelled_jobs": staged.cancelled_jobs,
        "consistency": {"missing": 0, "orphans": len(report["orphans"])},
    }


HANDLERS: dict[str, Handler] = {"backup": handle_backup, "restore": handle_restore}
