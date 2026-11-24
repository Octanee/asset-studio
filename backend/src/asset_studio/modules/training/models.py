"""Training datasets, their items with captions, and training runs (FR-070-FR-075)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from asset_studio.db import Base, utcnow, uuid7


class TrainingDataset(Base):
    __tablename__ = "training_dataset"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # The word that calls up the trained LoRA in a prompt; also the kohya class folder.
    trigger_word: Mapped[str] = mapped_column(String(40), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TrainingItem(Base):
    """One image: an approved version of the project or a file the user uploaded (RULE-017)."""

    __tablename__ = "training_item"
    __table_args__ = (
        CheckConstraint("source IN ('asset_version', 'upload')", name="source"),
        UniqueConstraint("dataset_id", "sha256", name="image"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_version.id", ondelete="RESTRICT"), nullable=True
    )
    # Uploads live in the library under projects/<id>/training/<dataset>/; versions are read
    # from their own (immutable) files.
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    caption: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrainingRun(Base):
    __tablename__ = "training_run"
    __table_args__ = (CheckConstraint("family_id IN ('sd15', 'sdxl')", name="family"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_dataset.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    family_id: Mapped[str] = mapped_column(String(16), nullable=False)
    base_model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    # Resolution, steps, rank, alpha, learning rate and seed, frozen at start.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    images: Mapped[int] = mapped_column(Integer, nullable=False)
    estimate: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    acknowledged_estimate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    output_name: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    output_model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_actor: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
