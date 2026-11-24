"""Audit service: the only way to write audit entries (RULE-006)."""

import uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from asset_studio.modules.audit.models import AuditEntry

Actor = Literal["user", "mcp", "system"]


def record(
    session: Session,
    *,
    actor: Actor,
    action: str,
    subject_type: str,
    subject_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        actor=actor,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        project_id=project_id,
        data=data or {},
    )
    session.add(entry)
    session.flush()
    return entry


def list_entries(
    session: Session,
    *,
    project_id: uuid.UUID | None = None,
    actor: str | None = None,
    action: str | None = None,
    subject_ids: list[uuid.UUID] | None = None,
    before: uuid.UUID | None = None,
    limit: int = 50,
) -> list[AuditEntry]:
    """Newest first; ``before`` is a cursor (an entry id, time-ordered UUIDv7)."""
    q = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
    if project_id:
        q = q.where(AuditEntry.project_id == project_id)
    if actor:
        q = q.where(AuditEntry.actor == actor)
    if action:
        q = q.where(AuditEntry.action == action)
    if subject_ids:
        q = q.where(AuditEntry.subject_id.in_(subject_ids))
    if before:
        q = q.where(AuditEntry.id < before)
    return list(session.scalars(q))


def list_actions(session: Session, *, project_id: uuid.UUID | None = None) -> list[str]:
    q = select(AuditEntry.action).distinct().order_by(AuditEntry.action)
    if project_id:
        q = q.where(AuditEntry.project_id == project_id)
    return list(session.scalars(q))
