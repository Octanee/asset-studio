"""App settings stored in the database (``setting``, Data-Model). Locations, the engine and
secrets come from the environment (``asset_studio.config``) and are only shown, never
changed here (D-58)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from asset_studio.db import Base, utcnow
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import Actor, record

# Every setting with its default. Unknown keys are refused.
DEFAULTS: dict[str, Any] = {
    # No new job starts while the queue is paused; backup and restore still run (WP-16).
    "queue_paused": False,
}


class AppSetting(Base):
    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


def get_all(session: Session) -> dict[str, Any]:
    stored = {s.key: s.value for s in session.scalars(select(AppSetting))}
    return {k: stored.get(k, v) for k, v in DEFAULTS.items()}


def queue_paused(session: Session) -> bool:
    row = session.get(AppSetting, "queue_paused")
    return bool(row.value) if row is not None else False


def update(session: Session, changes: dict[str, Any], actor: Actor) -> dict[str, Any]:
    """Only the user changes settings; every change is audited."""
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user changes settings.")
    unknown = sorted(set(changes) - set(DEFAULTS))
    if unknown:
        raise DomainError(422, "SETTING_UNKNOWN", f"Unknown settings: {', '.join(unknown)}.")
    before = get_all(session)
    for key, value in changes.items():
        if not isinstance(value, type(DEFAULTS[key])):
            raise DomainError(422, "SETTING_INVALID", f"Wrong type for setting {key}.")
        if before[key] == value:
            continue
        row = session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
        session.flush()
        record(
            session,
            actor=actor,
            action="setting.changed",
            subject_type="setting",
            data={"key": key, "from": before[key], "to": value},
        )
    return get_all(session)
