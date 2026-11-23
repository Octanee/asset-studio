"""Reference tables (FR-025, FR-026; see Data-Model)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from asset_studio.db import Base, utcnow, uuid7

ROLES = (
    "style",
    "character",
    "pose",
    "composition",
    "colour",
    "anatomy",
    "equipment",
    "background",
    "other",
)
TARGETS = ("style", "character", "job", "asset_version")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Reference(Base):
    __tablename__ = "reference"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="role"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Display name only (the original file name); never used in a path.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime: Mapped[str] = mapped_column(String(40), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ReferenceLink(Base):
    """A reference used by a style, a character, a job or a version (FR-026)."""

    __tablename__ = "reference_link"
    __table_args__ = (
        UniqueConstraint("reference_id", "target_type", "target_id"),
        CheckConstraint(_in("target_type", TARGETS), name="target_type"),
        CheckConstraint("weight >= 0 AND weight <= 2", name="weight"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reference.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
