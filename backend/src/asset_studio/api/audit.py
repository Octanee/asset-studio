"""Audit log API (FR-115, read-only)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from asset_studio.api.schemas import AuditOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.audit.service import list_entries

router = APIRouter()


@router.get("", response_model=list[AuditOut])
def list_audit(
    db: Annotated[Session, Depends(get_session)],
    _: CurrentActor,
    project_id: uuid.UUID | None = None,
    actor: str | None = None,
    action: str | None = None,
    before: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Any]:
    return list_entries(
        db, project_id=project_id, actor=actor, action=action, before=before, limit=limit
    )
