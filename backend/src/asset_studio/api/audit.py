"""Audit log API (FR-115, read-only). ``subject_id`` may repeat: an asset's trail is the
asset and its versions (FR-051)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from asset_studio.api.schemas import AuditOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.audit.service import list_actions, list_entries

router = APIRouter()


@router.get("", response_model=list[AuditOut])
def list_audit(
    db: Annotated[Session, Depends(get_session)],
    _: CurrentActor,
    project_id: uuid.UUID | None = None,
    actor: str | None = None,
    action: str | None = None,
    subject_id: Annotated[list[uuid.UUID] | None, Query(max_length=500)] = None,
    before: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Any]:
    return list_entries(
        db,
        project_id=project_id,
        actor=actor,
        action=action,
        subject_ids=subject_id,
        before=before,
        limit=limit,
    )


@router.get("/actions", response_model=list[str])
def audit_actions(
    db: Annotated[Session, Depends(get_session)],
    _: CurrentActor,
    project_id: uuid.UUID | None = None,
) -> list[str]:
    """The actions that appear in the log, for the audit view's filter (FR-115)."""
    return list_actions(db, project_id=project_id)
