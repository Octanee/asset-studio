"""Assets, versions and the lifecycle (FR-050 to FR-055, FR-061 to FR-064, RULE-003/005/019/020)."""

import io
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from asset_studio.errors import DomainError
from asset_studio.modules.assets import service
from asset_studio.modules.assets.models import AssetVersion
from asset_studio.modules.projects.config_schema import ProjectConfig
from asset_studio.modules.projects.service import create_project
from asset_studio.modules.storage.local import LocalStorage
from tests.conftest import MCP, ORIGIN, project_config

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"


def _project(db: Session) -> uuid.UUID:
    return create_project(db, ProjectConfig.model_validate(project_config()), "user").id


def _version(
    db: Session, storage: LocalStorage, project_id: uuid.UUID | None = None, name: str = "Squat"
) -> AssetVersion:
    pid = project_id or _project(db)
    asset = service.create_asset(db, pid, category="lower-body", name=name, actor="system")
    return service.add_version(
        db, storage, asset.id, io.BytesIO(PNG), mime="image/png", actor="system"
    )


def _to_review(db: Session, version: AssetVersion) -> None:
    service.transition(db, version.id, "start_processing", "system")
    service.transition(db, version.id, "processing_succeeded", "system")


def _act(client: TestClient, version_id: uuid.UUID, action: str, **extra: Any) -> Any:
    headers = extra.pop("headers", ORIGIN)
    return client.post(
        f"/api/v1/versions/{version_id}/transitions",
        json={"action": action, **extra},
        headers=headers,
    )


# --- versions and storage -----------------------------------------------------------------


def test_rule003_each_file_is_a_new_numbered_version(db: Session, storage: LocalStorage) -> None:
    v1 = _version(db, storage)
    v2 = service.add_version(
        db, storage, v1.asset_id, io.BytesIO(b"other"), mime="image/webp", actor="system"
    )
    assert (v1.number, v2.number) == (1, 2)
    assert v1.storage_key != v2.storage_key
    assert storage.path(v1.storage_key or "").read_bytes() == PNG
    assert v1.state == "generated"


def test_unknown_category_and_media_type_are_rejected(db: Session, storage: LocalStorage) -> None:
    pid = _project(db)
    with pytest.raises(DomainError) as err:
        service.create_asset(db, pid, category="nope", name="x", actor="user")
    assert err.value.code == "CATEGORY_UNKNOWN"
    asset = service.create_asset(db, pid, category="core", name="Plank", actor="user")
    with pytest.raises(DomainError) as err:
        service.add_version(db, storage, asset.id, io.BytesIO(b"x"), mime="text/html", actor="user")
    assert err.value.code == "MEDIA_TYPE_UNSUPPORTED"


def test_mcp_cannot_add_versions_directly(db: Session, storage: LocalStorage) -> None:
    v = _version(db, storage)
    with pytest.raises(DomainError) as err:
        service.add_version(db, storage, v.asset_id, io.BytesIO(PNG), mime="image/png", actor="mcp")
    assert err.value.code == "ACTOR_NOT_ALLOWED"


def test_slugs_are_unique_per_project(db: Session) -> None:
    pid = _project(db)
    a = service.create_asset(db, pid, category="core", name="Plank", actor="user")
    b = service.create_asset(db, pid, category="core", name="Plank", actor="user")
    assert (a.slug, b.slug) == ("plank", "plank-2")


def test_state_transition_history_is_append_only(db: Session, storage: LocalStorage) -> None:
    v = _version(db, storage)
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(
            text("UPDATE state_transition SET actor = 'x' WHERE asset_version_id = :id"),
            {"id": v.id},
        )


# --- lifecycle over the API ---------------------------------------------------------------


def test_review_flow_records_history_and_audit(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    v = _version(db, storage)
    _to_review(db, v)
    r = _act(client, v.id, "approve")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "approved"
    assert [h["transition_id"] for h in body["history"]] == ["T-01", "T-02", "T-03", "T-05"]
    audit = client.get("/api/v1/audit", params={"action": "asset_version.approve"}).json()
    assert audit[0]["subject_id"] == str(v.id) and audit[0]["actor"] == "user"


def test_invalid_transition_is_409(client: TestClient, db: Session, storage: LocalStorage) -> None:
    v = _version(db, storage)
    r = _act(client, v.id, "approve")
    assert r.status_code == 409
    assert r.json()["code"] == "LIFECYCLE_TRANSITION_NOT_ALLOWED"


def test_clients_cannot_request_system_transitions(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    v = _version(db, storage)
    assert _act(client, v.id, "start_processing").status_code == 422
    assert _act(client, v.id, "publish").status_code == 422  # publishing is WP-11's flow


def test_rule005_mcp_decisions_need_the_project_setting(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    v = _version(db, storage, pid)
    _to_review(db, v)
    r = _act(client, v.id, "approve", headers=MCP)
    assert r.status_code == 403 and r.json()["code"] == "MCP_NOT_ALLOWED"

    s = client.patch(
        f"/api/v1/projects/{pid}/settings", json={"mcp_can_decide": True}, headers=ORIGIN
    )
    assert s.status_code == 200
    r = _act(client, v.id, "reject", reason="hands look wrong", headers=MCP)
    assert r.status_code == 200 and r.json()["state"] == "rejected"
    assert r.json()["history"][-1]["actor"] == "mcp"
    # Reopening is never an MCP decision.
    assert _act(client, v.id, "reopen", headers=MCP).json()["code"] == "ACTOR_NOT_ALLOWED"


def test_fr063_rejected_version_returns_to_review(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    v = _version(db, storage)
    _to_review(db, v)
    _act(client, v.id, "reject")
    r = _act(client, v.id, "reopen")
    assert r.json()["state"] == "awaiting_review"


def test_rule020_withdraw_needs_reason_and_no_publication(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    v = _version(db, storage)
    _to_review(db, v)
    _act(client, v.id, "approve")
    r = _act(client, v.id, "withdraw")
    assert r.status_code == 422 and r.json()["code"] == "REASON_REQUIRED"
    r = _act(client, v.id, "withdraw", reason="wrong pose")
    assert r.json()["state"] == "awaiting_review"
    assert r.json()["history"][-1]["reason"] == "wrong pose"

    _act(client, v.id, "approve")
    service.transition(db, v.id, "publish", "user")
    service.transition(db, v.id, "archive", "user")
    service.transition(db, v.id, "restore", "user")
    assert _act(client, v.id, "withdraw", reason="x").status_code == 409


def test_fr053_archive_restores_previous_state(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    v = _version(db, storage)
    _to_review(db, v)
    _act(client, v.id, "approve")
    r = _act(client, v.id, "archive")
    assert (r.json()["state"], r.json()["previous_state"]) == ("archived", "approved")
    r = _act(client, v.id, "restore")
    assert (r.json()["state"], r.json()["previous_state"]) == ("approved", None)


def test_retry_after_processing_failure(db: Session, storage: LocalStorage) -> None:
    v = _version(db, storage)
    service.transition(db, v.id, "start_processing", "system")
    service.transition(db, v.id, "processing_failed", "system", data={"error": "timeout"})
    assert service.transition(db, v.id, "retry_processing", "user").state == "processing"


# --- permanent deletion -------------------------------------------------------------------


def test_fr054_delete_keeps_rows_and_removes_files(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    v = _version(db, storage)
    key = v.storage_key or ""
    _to_review(db, v)
    _act(client, v.id, "reject")

    r = client.delete(f"/api/v1/versions/{v.id}", headers=ORIGIN)
    assert r.status_code == 422 and r.json()["code"] == "CONFIRMATION_REQUIRED"
    r = client.delete(f"/api/v1/versions/{v.id}", params={"confirm": str(v.id)}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "deleted" and r.json()["deleted_at"]
    assert not storage.exists(key)
    assert client.get(f"/api/v1/versions/{v.id}/file").status_code == 410
    audit = client.get("/api/v1/audit", params={"action": "asset_version.deleted"}).json()
    assert audit[0]["data"]["sha256"] == v.sha256


def test_rule019_published_version_must_be_archived_first(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    v = _version(db, storage)
    _to_review(db, v)
    _act(client, v.id, "approve")
    service.transition(db, v.id, "publish", "user")
    confirm = {"confirm": str(v.id)}
    r = client.delete(f"/api/v1/versions/{v.id}", params=confirm, headers=ORIGIN)
    assert r.status_code == 409
    _act(client, v.id, "archive")
    r = client.delete(f"/api/v1/versions/{v.id}", params=confirm, headers=ORIGIN)
    assert r.status_code == 200


def test_only_the_user_deletes(client: TestClient, db: Session, storage: LocalStorage) -> None:
    v = _version(db, storage)
    r = client.delete(f"/api/v1/versions/{v.id}", params={"confirm": str(v.id)}, headers=MCP)
    assert r.status_code == 403


# --- browsing and files -------------------------------------------------------------------


def test_fr050_list_filters_and_cursor(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    squat = _version(db, storage, pid, "Squat")
    _version(db, storage, pid, "Lunge")
    plank = service.create_asset(db, pid, category="core", name="Plank 100%", actor="user")
    _to_review(db, squat)

    def names(**params: Any) -> list[str]:
        r = client.get("/api/v1/assets", params={"project_id": str(pid), **params})
        assert r.status_code == 200, r.text
        return [a["name"] for a in r.json()]

    assert names() == ["Plank 100%", "Lunge", "Squat"]
    assert names(category="core") == ["Plank 100%"]
    assert names(state="awaiting_review") == ["Squat"]
    assert names(q="100%") == ["Plank 100%"]
    assert names(q="unge") == ["Lunge"]
    assert names(before=str(plank.id), limit=1) == ["Lunge"]

    service.set_asset_archived(db, plank.id, True, "user")
    assert "Plank 100%" not in names()
    assert "Plank 100%" in names(include_archived="true")

    rows = client.get("/api/v1/assets", params={"project_id": str(pid)}).json()
    assert rows[0]["latest_version"]["number"] == 1 and rows[0]["version_count"] == 1


def test_fr051_asset_detail_lists_versions(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    v1 = _version(db, storage)
    service.add_version(db, storage, v1.asset_id, io.BytesIO(PNG), mime="image/png", actor="system")
    r = client.get(f"/api/v1/assets/{v1.asset_id}")
    assert [v["number"] for v in r.json()["versions"]] == [2, 1]


def test_fr055_download_original(client: TestClient, db: Session, storage: LocalStorage) -> None:
    v = _version(db, storage)
    r = client.get(f"/api/v1/versions/{v.id}/file", params={"download": "true"})
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"
    assert 'attachment; filename="squat-v1.png"' in r.headers["content-disposition"]
    assert "sandbox" in r.headers["content-security-policy"]
    assert client.get(f"/api/v1/versions/{v.id}/file", params={"size": "thumb"}).status_code == 404


def test_reading_requires_a_session(anon: TestClient) -> None:
    assert anon.get("/api/v1/assets").status_code == 401


def test_consistency_report_finds_missing_and_orphans(db: Session, storage: LocalStorage) -> None:
    v = _version(db, storage)
    storage.path(v.storage_key or "").unlink()
    orphan = f"{service.version_dir(uuid.uuid4(), uuid.uuid4(), 1)}/original.png"
    storage.put(orphan, io.BytesIO(PNG))
    report = service.consistency_report(db, storage)
    assert str(v.id) in report["missing"]
    assert orphan in report["orphans"]
