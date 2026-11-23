"""Engine status and control endpoints (FR-043)."""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from asset_studio.modules.audit.service import list_entries
from asset_studio.modules.providers.engine import EngineMonitor, get_engine_monitor
from asset_studio.modules.providers.fake import FakeProvider
from asset_studio.modules.providers.hostagent import HostAgentClient
from tests.conftest import MCP, ORIGIN


class Agent:
    def __init__(self) -> None:
        self.running = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/engine:start":
            self.running = True
        elif path == "/engine:stop":
            self.running = False
        if path == "/gpu":
            return httpx.Response(200, json={"available": True, "gpus": [{"name": "RTX"}]})
        return httpx.Response(200, json={"configured": True, "running": self.running, "pid": 42})


@pytest.fixture
def engine(client: TestClient) -> Iterator[tuple[EngineMonitor, Agent, FakeProvider]]:
    fake_agent = Agent()
    provider = FakeProvider(available=False)
    http = httpx.Client(base_url="http://agent", transport=httpx.MockTransport(fake_agent))
    monitor = EngineMonitor(provider, HostAgentClient("http://agent", "t", client=http), ttl=0)
    app: Any = client.app
    app.dependency_overrides[get_engine_monitor] = lambda: monitor
    yield monitor, fake_agent, provider
    app.dependency_overrides.pop(get_engine_monitor, None)


def test_fr043_engine_status_reports_availability_and_gpu(
    client: TestClient, engine: tuple[EngineMonitor, Agent, FakeProvider]
) -> None:
    body = client.get("/api/v1/system/engine").json()
    assert (body["provider"], body["available"], body["reason"]) == (
        "fake",
        False,
        "ENGINE_UNAVAILABLE",
    )
    assert body["agent"]["reachable"] is True
    assert body["agent"]["gpu"]["gpus"][0]["name"] == "RTX"


def test_user_starts_the_engine_and_it_is_audited(
    client: TestClient, db: Session, engine: tuple[EngineMonitor, Agent, FakeProvider]
) -> None:
    _, agent, provider = engine
    r = client.post("/api/v1/system/engine/start", headers=ORIGIN)
    assert r.status_code == 200
    assert agent.running is True
    assert r.json()["agent"]["engine"]["running"] is True
    provider.available = True
    assert client.get("/api/v1/system/engine").json()["available"] is True
    actions = [e.action for e in list_entries(db)]
    assert "engine.start" in actions


def test_only_the_user_controls_the_engine(
    client: TestClient, engine: tuple[EngineMonitor, Agent, FakeProvider]
) -> None:
    r = client.post("/api/v1/system/engine/stop", headers=MCP)
    assert (r.status_code, r.json()["code"]) == (403, "ACTOR_NOT_ALLOWED")
    assert client.post("/api/v1/system/engine/start").status_code == 403  # no Origin
    assert client.post("/api/v1/system/engine/reboot", headers=ORIGIN).status_code == 422


def test_engine_control_without_agent_token(client: TestClient) -> None:
    monitor = EngineMonitor(FakeProvider(), HostAgentClient("http://agent", ""))
    app: Any = client.app
    app.dependency_overrides[get_engine_monitor] = lambda: monitor
    try:
        body = client.get("/api/v1/system/engine").json()
        assert body["agent"] == {"configured": False}
        r = client.post("/api/v1/system/engine/start", headers=ORIGIN)
        assert (r.status_code, r.json()["code"]) == (409, "HOST_AGENT_NOT_CONFIGURED")
    finally:
        app.dependency_overrides.pop(get_engine_monitor, None)
