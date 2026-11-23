"""Pose table (FR-020 to FR-022; see Data-Model)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from asset_studio.db import Base, utcnow, uuid7

SOURCES = ("library", "editor", "detected")


class Pose(Base):
    __tablename__ = "pose"
    __table_args__ = (
        CheckConstraint("source IN ('library', 'editor', 'detected')", name="source"),
        CheckConstraint("aspect > 0.2 AND aspect < 5", name="aspect"),
        # Built-in poses have no project; every other pose belongs to one.
        CheckConstraint("(project_id IS NULL) = (source = 'library')", name="builtin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    view: Mapped[str] = mapped_column(String(16), nullable=False)
    # Canvas width / height the normalised keypoints refer to.
    aspect: Mapped[float] = mapped_column(Float, default=0.75, nullable=False)
    keypoints: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reference.id", ondelete="RESTRICT"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
