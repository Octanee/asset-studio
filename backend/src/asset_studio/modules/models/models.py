"""Model registry tables (FR-080, FR-083; see Data-Model)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from asset_studio.db import Base, utcnow, uuid7

KINDS = (
    "checkpoint",
    "lora",
    "controlnet",
    "ip_adapter",
    "clip_vision",
    "vae",
    "pose",
    "segmentation",
)
STATUSES = ("installed", "available", "missing", "downloading")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class ModelFamily(Base):
    __tablename__ = "model_family"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)


class Licence(Base):
    __tablename__ = "licence"
    __table_args__ = (
        CheckConstraint(_in("commercial_use", ("allowed", "forbidden", "unknown")), name="use"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    commercial_use: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Model(Base):
    """A catalogue model (``origin = 'catalogue'``) or a file found on disk (``'local'``)."""

    __tablename__ = "model"
    __table_args__ = (
        CheckConstraint(_in("kind", KINDS), name="kind"),
        CheckConstraint(_in("status", STATUSES), name="status"),
        CheckConstraint(_in("origin", ("catalogue", "local")), name="origin"),
        CheckConstraint(_in("verification", ("unverified", "ok", "mismatch")), name="verification"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    family_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_family.id", ondelete="RESTRICT"), nullable=True
    )
    licence_id: Mapped[str] = mapped_column(
        ForeignKey("licence.id", ondelete="RESTRICT"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Expected hash and size (catalogue); for a local file, the hash once it was verified.
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Size of the file on disk at the last scan; a change makes the hash unverified again.
    file_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    verification: Mapped[str] = mapped_column(String(16), default="unverified", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class LicenceAcknowledgement(Base):
    """The user confirmed using a model whose licence conflicts with the project (RULE-007)."""

    __tablename__ = "licence_acknowledgement"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(
        ForeignKey("model.id", ondelete="RESTRICT"), nullable=False
    )
    # The licence at the time; a different licence later needs a new confirmation.
    licence_id: Mapped[str] = mapped_column(
        ForeignKey("licence.id", ondelete="RESTRICT"), nullable=False
    )
    intended_use: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
