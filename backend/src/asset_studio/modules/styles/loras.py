"""LoRAs linked to a style or a character (FR-016, FR-075): generation with that style or
character uses them, at the link's strength, and adds their trigger words to the prompt."""

import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from asset_studio.db import Base, utcnow, uuid7
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.models.models import Model
from asset_studio.modules.models.service import get_model, sync_catalogue
from asset_studio.modules.styles.models import Character, Style
from asset_studio.modules.styles.service import get_character, get_style
from asset_studio.modules.training.service import trigger_words

Target = Literal["style", "character"]
MAX_LINKS = 2  # the workflows chain at most two LoRAs


class LoraLink(Base):
    __tablename__ = "lora_link"
    __table_args__ = (
        CheckConstraint("target_type IN ('style', 'character')", name="target_type"),
        CheckConstraint("strength >= 0 AND strength <= 2", name="strength"),
        UniqueConstraint("model_id", "target_type", "target_id", name="link"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    model_id: Mapped[str] = mapped_column(
        ForeignKey("model.id", ondelete="RESTRICT"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def _target(session: Session, target_type: Target, target_id: uuid.UUID) -> Style | Character:
    if target_type == "style":
        return get_style(session, target_id)
    return get_character(session, target_id)


def _rows(session: Session, target_type: str, target_id: uuid.UUID) -> list[LoraLink]:
    q = (
        select(LoraLink)
        .where(LoraLink.target_type == target_type, LoraLink.target_id == target_id)
        .order_by(LoraLink.created_at, LoraLink.id)
    )
    return list(session.scalars(q))


def _actor(actor: Actor) -> None:
    if actor not in ("user", "mcp"):
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Styles are changed by the user or Claude.")


def list_links(session: Session, target_type: Target, target_id: uuid.UUID) -> list[dict[str, Any]]:
    _target(session, target_type, target_id)
    rows = _rows(session, target_type, target_id)
    ids = [r.model_id for r in rows]
    models = {m.id: m for m in session.scalars(select(Model).where(Model.id.in_(ids)))}
    triggers = trigger_words(session, ids)
    return [
        {
            "model_id": r.model_id,
            "name": models[r.model_id].name,
            "family_id": models[r.model_id].family_id,
            "status": models[r.model_id].status,
            "strength": r.strength,
            "trigger_word": triggers.get(r.model_id),
        }
        for r in rows
    ]


def link(
    session: Session,
    target_type: Target,
    target_id: uuid.UUID,
    model_id: str,
    strength: float,
    actor: Actor,
) -> list[dict[str, Any]]:
    _actor(actor)
    target = _target(session, target_type, target_id)
    if target.archived_at is not None:
        raise DomainError(409, "TARGET_ARCHIVED", f"The {target_type} is archived.")
    sync_catalogue(session)
    model = get_model(session, model_id)
    if model.kind != "lora":
        raise DomainError(422, "MODEL_KIND_WRONG", f"{model.name} is not a LoRA.")
    if not 0 <= strength <= 2:
        raise DomainError(422, "STRENGTH_OUT_OF_RANGE", "Strength is between 0 and 2.")
    rows = _rows(session, target_type, target_id)
    existing = next((r for r in rows if r.model_id == model.id), None)
    if existing is None and len(rows) >= MAX_LINKS:
        raise DomainError(409, "LORA_LIMIT", f"A {target_type} uses at most {MAX_LINKS} LoRAs.")
    if existing is None:
        session.add(
            LoraLink(
                model_id=model.id, target_type=target_type, target_id=target_id, strength=strength
            )
        )
    else:
        existing.strength = strength
    session.flush()
    record(
        session,
        actor=actor,
        action=f"{target_type}.lora_linked",
        subject_type=target_type,
        subject_id=target_id,
        project_id=target.project_id,
        data={"model_id": model.id, "strength": strength},
    )
    return list_links(session, target_type, target_id)


def unlink(
    session: Session, target_type: Target, target_id: uuid.UUID, model_id: str, actor: Actor
) -> list[dict[str, Any]]:
    _actor(actor)
    target = _target(session, target_type, target_id)
    rows = _rows(session, target_type, target_id)
    row = next((r for r in rows if r.model_id == model_id), None)
    if row is None:
        raise DomainError(404, "LORA_LINK_NOT_FOUND", "This LoRA is not linked.")
    session.delete(row)
    session.flush()
    record(
        session,
        actor=actor,
        action=f"{target_type}.lora_unlinked",
        subject_type=target_type,
        subject_id=target_id,
        project_id=target.project_id,
        data={"model_id": model_id},
    )
    return list_links(session, target_type, target_id)


def linked(
    session: Session, style_id: uuid.UUID | None, character_id: uuid.UUID | None
) -> list[tuple[str, float]]:
    """(model id, strength) for a generation: the character's LoRAs, then the style's."""
    out: list[tuple[str, float]] = []
    for target_type, target_id in (("character", character_id), ("style", style_id)):
        if target_id is not None:
            out += [(r.model_id, r.strength) for r in _rows(session, target_type, target_id)]
    return out
