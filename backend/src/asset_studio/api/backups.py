"""Backup and restore (FR-111, FR-112). Both run as jobs; only the user starts them, and a
restore goes only into an empty data location."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from asset_studio.api.idempotency import Idem
from asset_studio.api.schemas import JobOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.errors import DomainError
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.storage.local import LocalStorage, get_storage
from asset_studio.modules.system import backup

router = APIRouter()
Db = Annotated[Session, Depends(get_session)]
Files = Annotated[LocalStorage, Depends(get_storage)]


class BackupOut(BaseModel):
    name: str
    bytes: int
    readable: bool
    created_at: str | None = None
    app_version: str | None = None
    schema_revision: str | None = None
    totals: dict[str, int] = {}
    models: int = 0


class BackupsOut(BaseModel):
    configured: bool
    items: list[BackupOut]


class RestoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


def _user_only(actor: str) -> None:
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user backs up and restores.")


@router.get("", response_model=BackupsOut)
def list_backups(_: CurrentActor) -> dict[str, Any]:
    return {"configured": backup.backups_dir().is_dir(), "items": backup.list_backups()}


@router.post("", response_model=JobOut, status_code=202)
def create_backup(db: Db, actor: CurrentActor, idem: Idem) -> Any:
    """Queue a backup: database, library files and the model list (no model files)."""
    _user_only(actor)

    def work() -> Any:
        return jobs.enqueue(db, "backup", {"actor": actor}, actor=actor)

    return idem.run(JobOut, 202, "backup", work)


@router.post(":restore", response_model=JobOut, status_code=202)
def restore_backup(db: Db, actor: CurrentActor, idem: Idem, files: Files, body: RestoreIn) -> Any:
    """Queue a restore of a backup from the backup folder into this empty data location."""
    _user_only(actor)

    def work() -> Any:
        backup.check_restorable(db.connection(), files.root, body.name)
        return jobs.enqueue(db, "restore", {"actor": actor, "name": body.name}, actor=actor)

    return idem.run(JobOut, 202, body.model_dump(), work)
