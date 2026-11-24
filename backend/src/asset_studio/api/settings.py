"""App settings (FR-110): what can be changed from the app. Locations come from the
environment and appear read-only in ``GET /system/status`` (D-58)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.system import settings

router = APIRouter()
Db = Annotated[Session, Depends(get_session)]


class SettingsOut(BaseModel):
    queue_paused: bool


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queue_paused: bool | None = None


@router.get("", response_model=SettingsOut)
def get_settings(db: Db, _: CurrentActor) -> dict[str, Any]:
    return settings.get_all(db)


@router.patch("", response_model=SettingsOut)
def update_settings(db: Db, actor: CurrentActor, body: SettingsUpdate) -> dict[str, Any]:
    """User only; every change is audited."""
    return settings.update(db, body.model_dump(exclude_none=True), actor)
