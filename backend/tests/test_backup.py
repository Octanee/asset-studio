"""Backup and restore (FR-111, FR-112, AC-009) and the queue pause (WP-16)."""

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.errors import DomainError
from asset_studio.modules.assets import service as assets
from asset_studio.modules.assets.models import AssetVersion, StateTransition
from asset_studio.modules.audit.models import AuditEntry
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.projects.config_schema import ProjectConfig
from asset_studio.modules.projects.models import Project
from asset_studio.modules.projects.service import create_project
from asset_studio.modules.review.models import ReviewComment
from asset_studio.modules.review.service import add_comment
from asset_studio.modules.storage.local import LocalStorage
from asset_studio.modules.system import backup
from asset_studio.modules.system.settings import queue_paused, update
from tests.conftest import project_config
from tests.test_jobs import _runner


def _png(colour: tuple[int, int, int] = (200, 40, 40)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 64), colour).save(out, "PNG")
    return out.getvalue()


def _library(connection: Connection, storage: LocalStorage) -> dict[str, Any]:
    """A project with an approved version, a comment and its audit trail; committed into a
    savepoint the test rolls back to empty the data location again."""
    with Session(bind=connection, join_transaction_mode="create_savepoint") as s:
        project = create_project(s, ProjectConfig.model_validate(project_config()), "user")
        asset = assets.create_asset(s, project.id, category="core", name="Plank", actor="system")
        v = assets.add_version(
            s, storage, asset.id, io.BytesIO(_png()), mime="image/png", actor="system"
        )
        assets.transition(s, v.id, "start_processing", "system")
        assets.transition(s, v.id, "processing_succeeded", "system")
        assets.transition(s, v.id, "approve", "user")
        add_comment(s, v.id, "Łokcie pod barkami.", "mcp")
        jobs.enqueue(s, "process", {"version_id": str(v.id)}, actor="user", project_id=project.id)
        s.commit()
        return {
            "project": project.id,
            "version": v.id,
            "sha256": v.sha256,
            "key": v.storage_key,
            "audit": s.scalar(select(func.count()).where(AuditEntry.project_id == project.id)),
        }


def _backup_and_empty(
    connection: Connection, storage: LocalStorage, folder: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    savepoint = connection.begin_nested()
    made = _library(connection, storage)
    result = backup.create_backup(connection, storage.root, folder)
    savepoint.rollback()  # the database is empty again
    return made, result


def test_ac009_backup_then_restore_into_an_empty_location(
    connection: Connection, storage: LocalStorage, tmp_path: Path
) -> None:
    made, result = _backup_and_empty(connection, storage, tmp_path / "backups")
    assert result["totals"]["files"] >= 1 and result["schema_revision"]
    assert [b["name"] for b in backup.list_backups(tmp_path / "backups")] == [result["name"]]

    fresh = LocalStorage(tmp_path / "fresh")
    assert backup.data_location_empty(connection, fresh.root)
    staged = backup.restore_backup(connection, fresh.root, tmp_path / "backups" / result["name"])
    assert backup.place_files(staged, fresh.root) == len(staged.keys)

    with Session(bind=connection, join_transaction_mode="create_savepoint") as s:
        project = s.get(Project, made["project"])
        assert project is not None and project.name == "Exerzio illustrations"
        v = s.get(AssetVersion, made["version"])
        assert v is not None and v.state == "approved" and v.sha256 == made["sha256"]
        assert fresh.exists(made["key"])
        restored = s.scalar(select(func.count()).where(AuditEntry.project_id == made["project"]))
        assert restored == made["audit"]
        history = s.scalars(
            select(StateTransition.to_state).where(StateTransition.asset_version_id == v.id)
        ).all()
        assert history[-1] == "approved"
        comment = s.scalars(
            select(ReviewComment).where(ReviewComment.asset_version_id == v.id)
        ).one()
        assert (comment.actor, comment.body) == ("mcp", "Łokcie pod barkami.")
        # The queued job came back cancelled: nothing starts by itself after a restore.
        states = s.scalars(
            text("SELECT state FROM job WHERE project_id = :p"), {"p": made["project"]}
        ).all()
        assert states == ["cancelled"]
        assert assets.consistency_report(s, fresh) == {"missing": [], "orphans": []}
    schemas = connection.scalars(text("SELECT nspname FROM pg_namespace")).all()
    assert backup.SCRATCH not in schemas


def test_restore_refuses_a_location_that_has_projects(
    connection: Connection, db: Session, storage: LocalStorage, tmp_path: Path
) -> None:
    _, result = _backup_and_empty(connection, storage, tmp_path / "backups")
    create_project(db, ProjectConfig.model_validate(project_config()), "user")
    db.flush()
    with pytest.raises(DomainError) as e:
        backup.restore_backup(connection, tmp_path / "fresh", tmp_path / "backups" / result["name"])
    assert e.value.code == "DATA_LOCATION_NOT_EMPTY"


def _rewrite(path: Path, change: Any) -> Path:
    """A copy of the archive with ``change(name, data)`` applied to each member."""
    out = path.with_name("asset-studio-backup-20990101-000000.zip")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(out, "w") as dst:
        for name in src.namelist():
            data = change(name, src.read(name))
            if data is not None:
                dst.writestr(name, data)
        extra = change("<extra>", b"")
        if extra:
            dst.writestr("files/projects/x/evil.txt", extra)
    return out


def test_restore_checks_integrity_before_touching_anything(
    connection: Connection, storage: LocalStorage, tmp_path: Path
) -> None:
    _, result = _backup_and_empty(connection, storage, tmp_path / "backups")
    path = tmp_path / "backups" / result["name"]
    fresh = tmp_path / "fresh"

    def flip(name: str, data: bytes) -> bytes | None:
        return data[:-1] + bytes([data[-1] ^ 1]) if name.startswith("files/") else data

    def smuggle(name: str, data: bytes) -> bytes | None:
        return b"surprise" if name == "<extra>" else data

    def newer(name: str, data: bytes) -> bytes | None:
        if name != backup.MANIFEST:
            return None if name == "<extra>" else data
        manifest = json.loads(data)
        manifest["schema_revision"] = "9999"
        return json.dumps(manifest).encode()

    for change, code in (
        (flip, "BACKUP_CORRUPT"),
        (smuggle, "BACKUP_INVALID"),
        (newer, "BACKUP_SCHEMA_UNKNOWN"),
    ):
        with pytest.raises(DomainError) as e:
            backup.restore_backup(connection, fresh, _rewrite(path, change))
        assert e.value.code == code
        assert not (fresh / "projects").exists()
    assert connection.scalar(text("SELECT count(*) FROM project")) == 0


def test_backup_names_are_never_paths() -> None:
    for name in ("../etc/passwd", "x.zip", "asset-studio-backup-20260101-000000.zip/../a"):
        with pytest.raises(DomainError) as e:
            backup.backup_path(name)
        assert e.value.code == "BACKUP_NAME_INVALID"


# --- queue pause ---------------------------------------------------------------------------


def test_a_paused_queue_starts_only_backup_and_restore(connection: Connection, db: Session) -> None:
    ran: list[str] = []
    handlers = {k: (lambda ctx, k=k: ran.append(k)) for k in ("process", "backup")}
    process = jobs.enqueue(db, "process", {}, actor="user")
    snapshot = jobs.enqueue(db, "backup", {}, actor="user")
    update(db, {"queue_paused": True}, "user")
    db.commit()
    assert queue_paused(db)
    runner = _runner(connection, handlers, paused=queue_paused)  # type: ignore[arg-type]
    runner.tick()
    db.expire_all()
    assert ran == ["backup"]
    assert jobs.get_job(db, snapshot.id).state == "completed"
    p = jobs.get_job(db, process.id)
    assert (p.state, p.wait_reason) == ("queued", "QUEUE_PAUSED")
    update(db, {"queue_paused": False}, "user")
    db.commit()
    runner.tick()
    db.expire_all()
    assert ran == ["backup", "process"]


def test_only_the_user_changes_settings(db: Session) -> None:
    for actor, changes, code in (
        ("mcp", {"queue_paused": True}, "ACTOR_NOT_ALLOWED"),
        ("user", {"nope": 1}, "SETTING_UNKNOWN"),
        ("user", {"queue_paused": "yes"}, "SETTING_INVALID"),
    ):
        with pytest.raises(DomainError) as e:
            update(db, changes, actor)  # type: ignore[arg-type]
        assert e.value.code == code


# --- API ------------------------------------------------------------------------------------


def test_api_settings_status_backups_and_dashboard(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    from tests.conftest import MCP, ORIGIN

    assert client.get("/api/v1/settings").json() == {"queue_paused": False}
    r = client.patch("/api/v1/settings", json={"queue_paused": True}, headers=MCP)
    assert r.json()["code"] == "ACTOR_NOT_ALLOWED"
    r = client.patch("/api/v1/settings", json={"queue_paused": True}, headers=ORIGIN)
    assert r.json() == {"queue_paused": True}
    assert client.patch("/api/v1/settings", json={"x": 1}, headers=ORIGIN).status_code == 422

    s = client.get("/api/v1/system/status").json()
    assert s["queue"]["paused"] is True and s["storage"]["empty"] is True
    assert s["database"]["schema_revision"] == s["database"]["head_revision"]
    assert s["mcp"] == {"configured": True, "port": 8411}
    assert "/" not in json.dumps(s["locations"]).replace("http://", "")  # no host paths

    assert client.post("/api/v1/backups", headers=MCP).json()["code"] == "ACTOR_NOT_ALLOWED"
    job = client.post("/api/v1/backups", headers=ORIGIN)
    assert job.status_code == 202 and job.json()["kind"] == "backup"
    bad = client.post("/api/v1/backups:restore", json={"name": "../x.zip"}, headers=ORIGIN)
    assert bad.json()["code"] == "BACKUP_NAME_INVALID"

    pid = create_project(db, ProjectConfig.model_validate(project_config()), "user").id
    db.commit()
    d = client.get(f"/api/v1/dashboard?project_id={pid}").json()
    assert d["attention"]["awaiting_review"] == 0 and d["latest_versions"] == []
    actions = client.get("/api/v1/audit/actions").json()
    assert "setting.changed" in actions and "job.enqueued" in actions
