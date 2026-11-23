"""Styles and characters (FR-010, FR-011, FR-015)."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from asset_studio.modules.audit.models import AuditEntry
from tests.conftest import MCP, ORIGIN, project_config


def _project(client: TestClient) -> str:
    r = client.post("/api/v1/projects", json=project_config(), headers=ORIGIN)
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


STYLE = {
    "name": "Flat vector",
    "attributes": {
        "description": "Clean flat shapes",
        "palette": ["#112233", "#FFAA00"],
        "rendering": "flat colour, no gradients",
        "lighting": "soft, even",
        "background": "plain white",
        "avoid": ["text", "watermark"],
        "extra": {"line_weight": "2 px"},
    },
}


def test_fr010_several_styles_per_project_with_attributes(client: TestClient) -> None:
    pid = _project(client)
    first = client.post(f"/api/v1/projects/{pid}/styles", json=STYLE, headers=ORIGIN)
    assert first.status_code == 201, first.text
    assert first.json()["attributes"]["extra"] == {"line_weight": "2 px"}
    assert first.json()["version"] == 1
    second = client.post(f"/api/v1/projects/{pid}/styles", json={"name": "Sketch"}, headers=ORIGIN)
    assert second.status_code == 201
    names = [s["name"] for s in client.get(f"/api/v1/projects/{pid}/styles").json()]
    assert names == ["Flat vector", "Sketch"]


def test_fr011_attributes_are_validated(client: TestClient) -> None:
    pid = _project(client)
    for attributes in (
        {"palette": ["red"]},
        {"extra": {"Not Snake": "x"}},
        {"avoid": [""]},
        {"unknown_field": 1},
    ):
        r = client.post(
            f"/api/v1/projects/{pid}/styles",
            json={"name": "Bad", "attributes": attributes},
            headers=ORIGIN,
        )
        assert r.status_code == 422, attributes


def test_style_names_are_unique_per_project(client: TestClient) -> None:
    pid = _project(client)
    client.post(f"/api/v1/projects/{pid}/styles", json=STYLE, headers=ORIGIN)
    r = client.post(f"/api/v1/projects/{pid}/styles", json=STYLE, headers=ORIGIN)
    assert (r.status_code, r.json()["code"]) == (409, "STYLE_NAME_TAKEN")


def test_update_bumps_version_and_is_audited(client: TestClient, db: Session) -> None:
    pid = _project(client)
    sid = client.post(f"/api/v1/projects/{pid}/styles", json=STYLE, headers=ORIGIN).json()["id"]
    attrs = {**STYLE["attributes"], "lighting": "hard rim light"}  # type: ignore[dict-item]
    r = client.patch(f"/api/v1/styles/{sid}", json={"attributes": attrs}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["version"] == 2
    # Saving the same values again is not a new version.
    again = client.patch(f"/api/v1/styles/{sid}", json={"attributes": attrs}, headers=ORIGIN)
    assert again.json()["version"] == 2
    actions = db.scalars(
        select(AuditEntry.action).where(AuditEntry.subject_id == uuid.UUID(sid))
    ).all()
    assert list(actions) == ["style.created", "style.updated"]


def test_archive_hides_style_and_blocks_edits(client: TestClient) -> None:
    pid = _project(client)
    sid = client.post(f"/api/v1/projects/{pid}/styles", json=STYLE, headers=ORIGIN).json()["id"]
    assert client.post(f"/api/v1/styles/{sid}/archive", headers=ORIGIN).json()["archived_at"]
    assert client.get(f"/api/v1/projects/{pid}/styles").json() == []
    assert len(client.get(f"/api/v1/projects/{pid}/styles?include_archived=true").json()) == 1
    r = client.patch(f"/api/v1/styles/{sid}", json={"name": "New"}, headers=ORIGIN)
    assert r.json()["code"] == "STYLE_ARCHIVED"
    restored = client.post(f"/api/v1/styles/{sid}/restore", headers=ORIGIN).json()
    assert restored["archived_at"] is None


def test_fr015_characters(client: TestClient) -> None:
    pid = _project(client)
    r = client.post(
        f"/api/v1/projects/{pid}/characters",
        json={
            "name": "Ola",
            "description": "Trainer in her thirties",
            "attributes": {"traits": {"hair": "short dark bob"}, "avoid": ["glasses"]},
        },
        headers=ORIGIN,
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = client.patch(
        f"/api/v1/characters/{cid}", json={"description": "Trainer, 35"}, headers=ORIGIN
    )
    assert (r.json()["description"], r.json()["version"]) == ("Trainer, 35", 2)
    assert [c["name"] for c in client.get(f"/api/v1/projects/{pid}/characters").json()] == ["Ola"]


def test_claude_may_edit_styles_and_unknown_ids_are_404(client: TestClient) -> None:
    pid = _project(client)
    r = client.post(f"/api/v1/projects/{pid}/styles", json=STYLE, headers=MCP)
    assert r.status_code == 201
    assert client.get(f"/api/v1/styles/{uuid.uuid4()}").json()["code"] == "STYLE_NOT_FOUND"
    missing = client.get(f"/api/v1/projects/{uuid.uuid4()}/styles")
    assert missing.json()["code"] == "PROJECT_NOT_FOUND"


def test_writes_need_the_origin_header(client: TestClient) -> None:
    pid = _project(client)
    r = client.post(f"/api/v1/projects/{pid}/styles", json=STYLE)
    assert r.status_code == 403
