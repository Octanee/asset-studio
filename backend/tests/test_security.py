"""ADR-012 / NFR-005 / RULE-018: Host allow-list, Origin checks, actor from credential."""

from fastapi.testclient import TestClient

from tests.conftest import MCP, ORIGIN, project_config


def test_unknown_host_is_rejected(anon: TestClient) -> None:
    r = anon.get("/api/v1/system/health", headers={"Host": "evil.example"})
    assert r.status_code == 400
    assert r.json()["code"] == "HOST_NOT_ALLOWED"


def test_requests_without_credentials_are_rejected(anon: TestClient) -> None:
    r = anon.get("/api/v1/projects")
    assert r.status_code == 401
    assert r.json()["code"] == "AUTH_REQUIRED"


def test_invalid_bearer_token_is_rejected(anon: TestClient) -> None:
    r = anon.get("/api/v1/projects", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_session_cookie_is_strict_and_http_only(anon: TestClient) -> None:
    r = anon.get("/api/v1/session")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_unsafe_request_with_cookie_needs_allowed_origin(client: TestClient) -> None:
    assert client.post("/api/v1/projects", json=project_config()).status_code == 403
    bad = client.post(
        "/api/v1/projects", json=project_config(), headers={"Origin": "http://evil.example"}
    )
    assert bad.status_code == 403 and bad.json()["code"] == "ORIGIN_NOT_ALLOWED"
    assert client.post("/api/v1/projects", json=project_config(), headers=ORIGIN).status_code == 201


def test_mcp_token_maps_to_mcp_actor_and_cannot_create_projects(client: TestClient) -> None:
    r = client.post("/api/v1/projects", json=project_config(), headers=MCP)
    assert r.status_code == 403
    assert r.json()["code"] == "ACTOR_NOT_ALLOWED"
