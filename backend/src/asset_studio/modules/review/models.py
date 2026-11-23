"""Review tables (see Data-Model)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from asset_studio.db import Base, utcnow, uuid7

COMMENT_ACTORS = ("user", "mcp")
MAX_COMMENT = 4000


class ReviewComment(Base):
    """A comment on a version by the user or Claude (MCP). Append-only, like the audit."""

    __tablename__ = "review_comment"
    __table_args__ = (
        CheckConstraint(f"actor IN ({', '.join(repr(a) for a in COMMENT_ACTORS)})", name="actor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    asset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_version.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(String(MAX_COMMENT), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
