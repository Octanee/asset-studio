from fastapi.testclient import TestClient

from asset_studio_host_agent.app import AgentSettings, create_app


def client(token: str = "secret-token") -> TestClient:
    return TestClient(create_app(AgentSettings(token=token)))


def test_health_requires_token() -> None:
    assert client().get("/health").status_code == 401
    assert client().get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_health_with_token() -> None:
    r = client().get("/health", headers={"Authorization": "Bearer secret-token"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_empty_token_rejects_everything() -> None:
    assert client(token="").get("/health", headers={"Authorization": "Bearer "}).status_code == 401
