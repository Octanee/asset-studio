"""Dashboard summary for one project (FR-100)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from asset_studio.api.backups import BackupOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.projects.service import get_project
from asset_studio.modules.system import status

router = APIRouter()


class Attention(BaseModel):
    awaiting_review: int
    processing_failed: int
    failed_jobs: int
    licence_warnings: int
    backup_due: bool


class LatestVersion(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    asset_name: str
    category: str
    number: int
    state: str
    created_at: datetime


class FailedJob(BaseModel):
    id: uuid.UUID
    kind: str
    finished_at: datetime | None
    code: str | None
    message: str | None


class DashboardOut(BaseModel):
    versions_by_state: dict[str, int]
    attention: Attention
    latest_versions: list[LatestVersion]
    failed_jobs: list[FailedJob]
    last_backup: BackupOut | None


@router.get("", response_model=DashboardOut)
def dashboard(
    db: Annotated[Session, Depends(get_session)], _: CurrentActor, project_id: uuid.UUID
) -> dict[str, Any]:
    get_project(db, project_id)  # 404 for an unknown project
    return status.dashboard(db, project_id)
