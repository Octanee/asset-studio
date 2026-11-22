"""Project tables (see Data-Model)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from asset_studio.db import Base, utcnow, uuid7


class Project(Base):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    intended_use: Mapped[str] = mapped_column(String(16), nullable=False)
    mcp_can_decide: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProjectConfigVersion(Base):
    __tablename__ = "project_config_version"
    __table_args__ = (UniqueConstraint("project_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_actor: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectDraft(Base):
    """A configuration proposed by MCP (or the user) that is not a project yet (FR-008)."""

    __tablename__ = "project_draft"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    description: Mapped[str] = mapped_column(String(4000), default="", nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    missing: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    created_by_actor: Mapped[str] = mapped_column(String(16), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
