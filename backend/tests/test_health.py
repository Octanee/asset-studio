from fastapi.testclient import TestClient

from asset_studio import __version__
from asset_studio.main import create_app


def test_health_reports_ok_and_version() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_default_host_is_loopback() -> None:
    from asset_studio.config import Settings

    assert Settings().host == "127.0.0.1"  # NFR-005
