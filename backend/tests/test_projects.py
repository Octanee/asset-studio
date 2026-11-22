"""FR-001 to FR-008, RULE-005, RULE-010, RULE-014; AC-010."""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import MCP, ORIGIN, project_config


def create(client: TestClient, **overrides: object) -> dict[str, Any]:
    r = client.post("/api/v1/projects", json=project_config(**overrides), headers=ORIGIN)
    assert r.status_code == 201, r.text
    return r.json()


def test_fr001_create_project_with_defaults(client: TestClient) -> None:
    p = create(client)
    assert p["slug"] == "exerzio-illustrations"
    assert p["mcp_can_decide"] is False  # RULE-005 default off
    assert p["current_config_version"] == 1
    assert p["config"]["output"]["format"] == "png"


def test_fr001_slugs_are_unique(client: TestClient) -> None:
    create(client)
    assert create(client)["slug"] == "exerzio-illustrations-2"


def test_fr007_invalid_config_is_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/v1/projects", json=project_config(naming="{asset}/{oops}"), headers=ORIGIN
    )
    assert r.status_code == 422


def test_fr007_config_change_creates_version(client: TestClient) -> None:
    p = create(client)
    cfg = p["config"] | {"description": "Exercises for the app"}
    r = client.put(f"/api/v1/projects/{p['id']}/config", json={"config": cfg}, headers=ORIGIN)
    assert r.status_code == 200
    assert r.json()["current_config_version"] == 2
    versions = client.get(f"/api/v1/projects/{p['id']}/config/versions").json()
    assert [v["version"] for v in versions] == [2, 1]


def test_fr007_breaking_change_needs_acknowledgement(client: TestClient) -> None:
    p = create(client)
    cfg = p["config"] | {"categories": [{"slug": "core", "name": "Core"}]}
    r = client.put(f"/api/v1/projects/{p['id']}/config", json={"config": cfg}, headers=ORIGIN)
    assert r.status_code == 409
    assert r.json()["code"] == "CONFIG_BREAKING_CHANGE"
    assert "categories removed: lower-body" in r.json()["changes"]
    ok = client.put(
        f"/api/v1/projects/{p['id']}/config",
        json={"config": cfg, "acknowledge_breaking": True},
        headers=ORIGIN,
    )
    assert ok.status_code == 200


def test_rule005_only_user_changes_mcp_permission_and_it_is_audited(client: TestClient) -> None:
    p = create(client)
    url = f"/api/v1/projects/{p['id']}/settings"
    assert client.patch(url, json={"mcp_can_decide": True}, headers=MCP).status_code == 403
    r = client.patch(url, json={"mcp_can_decide": True}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["mcp_can_decide"] is True
    audit = client.get(
        "/api/v1/audit", params={"project_id": p["id"], "action": "project.mcp_can_decide_changed"}
    ).json()
    assert len(audit) == 1 and audit[0]["actor"] == "user" and audit[0]["data"] == {"value": True}


def test_fr003_archive_and_restore(client: TestClient) -> None:
    p = create(client)
    client.post(f"/api/v1/projects/{p['id']}/archive", headers=ORIGIN)
    assert client.get("/api/v1/projects").json() == []
    assert len(client.get("/api/v1/projects", params={"include_archived": True}).json()) == 1
    client.post(f"/api/v1/projects/{p['id']}/restore", headers=ORIGIN)
    assert len(client.get("/api/v1/projects").json()) == 1


def test_fr004_clone_copies_configuration(client: TestClient) -> None:
    p = create(client)
    r = client.post(
        f"/api/v1/projects/{p['id']}/clone", json={"name": "Exerzio icons"}, headers=ORIGIN
    )
    assert r.status_code == 201
    clone = r.json()
    assert clone["name"] == "Exerzio icons"
    assert clone["config"]["categories"] == p["config"]["categories"]


def test_ac010_export_then_import_creates_valid_project(client: TestClient) -> None:
    p = create(client)
    doc = client.get(f"/api/v1/projects/{p['id']}/config/export").json()
    assert doc["format"] == "asset-studio-project"
    r = client.post("/api/v1/projects/import", json=doc, headers=ORIGIN)
    assert r.status_code == 201
    assert r.json()["config"] == p["config"]


def test_fr006_import_reports_invalid_configuration(client: TestClient) -> None:
    doc = {
        "format": "asset-studio-project",
        "format_version": 1,
        "config": project_config(languages=["polish"]),
    }
    r = client.post("/api/v1/projects/import", json=doc, headers=ORIGIN)
    assert r.status_code == 422
    assert r.json()["code"] == "CONFIG_INVALID"
    assert any("language" in e["msg"] for e in r.json()["errors"])


def test_fr006_import_rejects_unknown_format(client: TestClient) -> None:
    r = client.post("/api/v1/projects/import", json={"format": "other"}, headers=ORIGIN)
    assert r.json()["code"] == "IMPORT_FORMAT_UNSUPPORTED"


def test_fr008_mcp_draft_needs_user_confirmation(client: TestClient) -> None:
    draft = client.post(
        "/api/v1/projects/drafts",
        headers=MCP,
        json={
            "description": "Illustrations of bodyweight exercises",
            "config": {"name": "Exerzio", "type": "illustration"},
            "assumptions": ["Square 1024 px output"],
            "missing": ["intended use"],
        },
    ).json()
    assert draft["created_by_actor"] == "mcp" and draft["status"] == "pending"
    assert any(p["loc"] == ["intended_use"] for p in draft["problems"])  # missing info is shown
    full = project_config(name="Exerzio")
    url = f"/api/v1/projects/drafts/{draft['id']}/confirm"
    assert client.post(url, json={"config": full}, headers=MCP).status_code == 403  # RULE-010
    r = client.post(url, json={"config": full}, headers=ORIGIN)
    assert r.status_code == 201
    assert client.get(f"/api/v1/projects/drafts/{draft['id']}").json()["status"] == "confirmed"
    assert (
        client.post(url, json={"config": full}, headers=ORIGIN).json()["code"]
        == "DRAFT_NOT_PENDING"
    )


def test_unknown_project_is_404(client: TestClient) -> None:
    r = client.get("/api/v1/projects/00000000-0000-7000-8000-000000000000")
    assert r.status_code == 404 and r.json()["code"] == "PROJECT_NOT_FOUND"
