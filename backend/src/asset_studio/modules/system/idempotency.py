"""Idempotency keys (API-Architecture): a POST that creates jobs or publications can carry an
``Idempotency-Key``; repeating it returns the first answer instead of doing the work twice.
MCP must send one, because an agent may retry a call whose answer it did not see.

The key row is written in the request's own transaction: a failed request stores nothing, and
a concurrent request with the same key waits on the unique index, then replays the answer.
"""

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from asset_studio.db import Base, utcnow, uuid7
from asset_studio.errors import DomainError

KEY = re.compile(r"^[A-Za-z0-9._:-]{8,200}$")
KEEP = timedelta(hours=24)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_key"
    __table_args__ = (UniqueConstraint("actor", "key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    request: Mapped[str] = mapped_column(String(64), nullable=False)  # hash of method, path, body
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response: Mapped[Any] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def fingerprint(method: str, path: str, body: str) -> str:
    return hashlib.sha256(f"{method} {path} {body}".encode()).hexdigest()


@dataclass
class Claim:
    row: IdempotencyKey
    replay: tuple[int, Any] | None = None


def _check(row: IdempotencyKey, request: str) -> Claim:
    if row.request != request:
        raise DomainError(
            422,
            "IDEMPOTENCY_KEY_REUSED",
            "This Idempotency-Key was used for a different request.",
        )
    if row.status_code is None:  # only possible within the same transaction
        raise DomainError(409, "IDEMPOTENCY_IN_PROGRESS", "The same request is still running.")
    return Claim(row, (row.status_code, row.response))


def claim(session: Session, actor: str, key: str, request: str) -> Claim:
    """Reserve ``key`` for this request, or return the stored answer of an earlier one."""
    if not KEY.match(key):
        raise DomainError(
            422, "IDEMPOTENCY_KEY_INVALID", "Use 8 to 200 letters, digits or . _ : - as the key."
        )
    q = select(IdempotencyKey).where(IdempotencyKey.actor == actor, IdempotencyKey.key == key)
    row = session.scalar(q)
    if row is not None and utcnow() - row.created_at > KEEP:
        session.delete(row)
        session.flush()
        row = None
    if row is not None:
        return _check(row, request)
    row = IdempotencyKey(actor=actor, key=key, request=request)
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        # Another request with this key committed first: answer as it did.
        existing = session.scalar(q.execution_options(populate_existing=True))
        if existing is None:  # pragma: no cover - deleted in between
            raise DomainError(409, "IDEMPOTENCY_IN_PROGRESS", "Try again.") from None
        return _check(existing, request)
    return Claim(row)


def store(session: Session, claim_: Claim, status_code: int, response: Any) -> None:
    claim_.row.status_code, claim_.row.response = status_code, response
    session.flush()
