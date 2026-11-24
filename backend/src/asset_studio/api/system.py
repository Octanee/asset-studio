"""System endpoints: liveness, the generation engine (FR-043) and the system status (WP-16):
database, queue, storage, consistency, backups and locations, without host paths."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from asset_studio import __version__
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import record
from asset_studio.modules.providers.engine import EngineMonitor, get_engine_monitor
from asset_studio.modules.providers.hostagent import EngineAction
from asset_studio.modules.storage.local import LocalStorage, get_storage
from asset_studio.modules.system import status as system_status

router = APIRouter()
Engine = Annotated[EngineMonitor, Depends(get_engine_monitor)]


class Health(BaseModel):
    status: str
    version: str


class DeviceOut(BaseModel):
    name: str
    vram_total_mb: int | None
    vram_free_mb: int | None


class EngineOut(BaseModel):
    provider: str
    engine: str
    available: bool
    version: str | None
    reason: str | None
    detail: str | None
    devices: list[DeviceOut]
    features: list[str]
    # Host agent view: configured, reachable, engine process and GPU (nvidia-smi).
    agent: dict[str, Any]


@router.get("/health", response_model=Health)
def health() -> Health:
    """Liveness probe: the API process is up."""
    return Health(status="ok", version=__version__)


@router.get("/engine", response_model=EngineOut)
def engine_status(_: CurrentActor, engine: Engine) -> dict[str, Any]:
    """Is the engine reachable, which version, which GPU (FR-043)."""
    return engine.status()


@router.post("/engine/{action}", response_model=EngineOut)
def engine_control(
    action: EngineAction,
    actor: CurrentActor,
    engine: Engine,
    db: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Start, stop or restart the engine through the host agent. User only: Claude (MCP)
    and the system cannot switch the engine."""
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user can control the engine.")
    result = engine.control(action)
    record(db, actor=actor, action=f"engine.{action}", subject_type="engine", data=result)
    return engine.status()


class StatusOut(BaseModel):
    api: Health
    engine: EngineOut
    database: dict[str, Any]
    queue: dict[str, Any]
    storage: dict[str, Any]
    consistency: dict[str, Any]
    backups: dict[str, Any]
    locations: dict[str, Any]
    mcp: dict[str, Any]


@router.get("/status", response_model=StatusOut)
def status(
    _: CurrentActor,
    engine: Engine,
    db: Annotated[Session, Depends(get_session)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
) -> dict[str, Any]:
    """Component health for the System status screen (NFR-003)."""
    return {
        "api": Health(status="ok", version=__version__),
        "engine": engine.status(),
        **system_status.status(db, storage),
    }
