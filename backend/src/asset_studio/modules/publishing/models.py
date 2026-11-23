"""Publishing tables (FR-090 to FR-095; see Data-Model)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from asset_studio.db import Base, utcnow, uuid7


class ExportPreset(Base):
    """How versions become files: format, sizes, naming, folders, optimisation, metadata."""

    __tablename__ = "export_preset"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ExportTarget(Base):
    """A folder under one of the configured export roots (ADR-013)."""

    __tablename__ = "export_target"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    root: Mapped[str] = mapped_column(String(300), nullable=False)
    subdir: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PublicationPlan(Base):
    """The files a publish would write, with the ones that already exist (DD-006, RULE-004).
    A plan is used once."""

    __tablename__ = "publication_plan"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    preset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("export_preset.id", ondelete="RESTRICT"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("export_target.id", ondelete="RESTRICT"), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    skipped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class Publication(Base):
    """One version written to one target through one preset (FR-093)."""

    __tablename__ = "publication"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    asset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_version.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("export_target.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    preset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("export_preset.id", ondelete="RESTRICT"), nullable=False
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("publication_plan.id", ondelete="RESTRICT"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PublicationFile(Base):
    __tablename__ = "publication_file"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    publication_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publication.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    overwrote_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirmed_overwrite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CurrentPublication(Base):
    """The asset's currently published version in a target (D-41)."""

    __tablename__ = "current_publication"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset.id", ondelete="RESTRICT"), primary_key=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("export_target.id", ondelete="RESTRICT"), primary_key=True
    )
    publication_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publication.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
