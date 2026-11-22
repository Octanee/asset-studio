"""Test setup: a real PostgreSQL database (ASSET_STUDIO_TEST_DATABASE_URL), migrated once,
with every test wrapped in a transaction that is rolled back (the audit log is append-only,
so tables cannot be cleaned with DELETE)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.modules.storage.local import LocalStorage, get_storage

TEST_DB = os.environ.get("ASSET_STUDIO_TEST_DATABASE_URL", "")
os.environ.update(
    ASSET_STUDIO_SESSION_SECRET="test-session-secret",
    ASSET_STUDIO_MCP_TOKEN="test-mcp-token",
    ASSET_STUDIO_WORKER_TOKEN="test-worker-token",
    ASSET_STUDIO_LOG_JSON="false",
)
if TEST_DB:
    os.environ["ASSET_STUDIO_DATABASE_URL"] = TEST_DB
os.environ.setdefault("ASSET_STUDIO_DATA_DIR", os.path.join(os.path.dirname(__file__), ".data"))

ORIGIN = {"Origin": "http://127.0.0.1:8480"}
MCP = {"Authorization": "Bearer test-mcp-token"}


@pytest.fixture(scope="session")
def migrated() -> Iterator[None]:
    if not TEST_DB:
        pytest.skip("ASSET_STUDIO_TEST_DATABASE_URL is not set")
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    cfg.attributes["database_url"] = TEST_DB
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def connection(migrated: None) -> Iterator[Connection]:
    engine = create_engine(TEST_DB)
    with engine.connect() as conn:
        tx = conn.begin()
        yield conn
        tx.rollback()
    engine.dispose()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        yield session


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "data")


@pytest.fixture
def client(connection: Connection, storage: LocalStorage) -> Iterator[TestClient]:
    from asset_studio.db import get_session
    from asset_studio.main import create_app

    app = create_app()
    app.dependency_overrides[get_storage] = lambda: storage

    def _session() -> Iterator[Session]:
        with Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/api/v1/session").status_code == 200
        yield c


@pytest.fixture
def anon() -> TestClient:
    from asset_studio.main import create_app

    return TestClient(create_app(), base_url="http://127.0.0.1")


def project_config(**overrides: object) -> dict[str, object]:
    cfg: dict[str, object] = {
        "name": "Exerzio illustrations",
        "type": "illustration",
        "languages": ["pl", "en"],
        "intended_use": "commercial",
        "categories": [
            {"slug": "lower-body", "name": "Lower body"},
            {"slug": "core", "name": "Core"},
        ],
    }
    cfg.update(overrides)
    return cfg
