"""Styles and characters per project (FR-010, FR-011, FR-015).

A style is described by text attributes and/or style references (the references module
owns the links). Project-specific attributes go into ``extra`` (FR-011). Every change is
audited (RULE-006) and bumps ``version``, so a generation can record what it used.
"""

import re
import uuid
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from asset_studio.db import utcnow
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.projects.service import get_project
from asset_studio.modules.styles.models import Character, Style

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
Short = Annotated[str, StringConstraints(max_length=500)]
Item = Annotated[str, StringConstraints(min_length=1, max_length=200)]
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def _check_named(value: dict[str, str]) -> dict[str, str]:
    for key, text in value.items():
        if not _KEY.fullmatch(key):
            raise ValueError(f"attribute name {key!r} must be snake_case (a-z, 0-9, _)")
        if len(text) > 500:
            raise ValueError(f"attribute {key!r} is longer than 500 characters")
    return value


class StyleAttributes(BaseModel):
    # Unknown keys are an error: project-specific attributes go into `extra` (FR-011).
    model_config = ConfigDict(extra="forbid")
    description: str = Field(default="", max_length=2000)
    palette: list[HexColor] = Field(default_factory=list, max_length=16)
    rendering: Short = ""
    lighting: Short = ""
    background: Short = ""
    # Negative constraints (the "avoid" list).
    avoid: list[Item] = Field(default_factory=list, max_length=50)
    # Project-specific attributes (FR-011).
    extra: dict[str, str] = Field(default_factory=dict, max_length=30)

    @field_validator("extra")
    @classmethod
    def _extra(cls, value: dict[str, str]) -> dict[str, str]:
        return _check_named(value)


class CharacterAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    traits: dict[str, str] = Field(default_factory=dict, max_length=30)
    avoid: list[Item] = Field(default_factory=list, max_length=50)

    @field_validator("traits")
    @classmethod
    def _traits(cls, value: dict[str, str]) -> dict[str, str]:
        return _check_named(value)


def _user_or_mcp(actor: Actor) -> None:
    if actor not in ("user", "mcp"):
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Styles are edited by the user or Claude.")


def _flush_unique(session: Session, kind: str) -> None:
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise DomainError(
            409, f"{kind.upper()}_NAME_TAKEN", f"A {kind} with this name already exists."
        ) from exc


def _get[Row: (Style, Character)](session: Session, model: type[Row], row_id: uuid.UUID) -> Row:
    row = session.get(model, row_id)
    if row is None:
        kind = model.__tablename__
        raise DomainError(404, f"{kind.upper()}_NOT_FOUND", f"{kind.capitalize()} not found.")
    return row


def _list[Row: (Style, Character)](
    session: Session, model: type[Row], project_id: uuid.UUID, include_archived: bool
) -> list[Row]:
    get_project(session, project_id)
    q = select(model).where(model.project_id == project_id).order_by(model.name)
    if not include_archived:
        q = q.where(model.archived_at.is_(None))
    return list(session.scalars(q))


def _open_project(session: Session, project_id: uuid.UUID) -> uuid.UUID:
    project = get_project(session, project_id)
    if project.archived_at is not None:
        raise DomainError(409, "PROJECT_ARCHIVED", "The project is archived.")
    return project.id


def get_style(session: Session, style_id: uuid.UUID) -> Style:
    return _get(session, Style, style_id)


def get_character(session: Session, character_id: uuid.UUID) -> Character:
    return _get(session, Character, character_id)


def list_styles(
    session: Session, project_id: uuid.UUID, include_archived: bool = False
) -> list[Style]:
    return _list(session, Style, project_id, include_archived)


def list_characters(
    session: Session, project_id: uuid.UUID, include_archived: bool = False
) -> list[Character]:
    return _list(session, Character, project_id, include_archived)


def _created(session: Session, row: Style | Character, actor: Actor) -> None:
    session.add(row)
    _flush_unique(session, row.__tablename__)
    record(
        session,
        actor=actor,
        action=f"{row.__tablename__}.created",
        subject_type=row.__tablename__,
        subject_id=row.id,
        project_id=row.project_id,
        data={"name": row.name},
    )


def create_style(
    session: Session, project_id: uuid.UUID, name: str, attributes: StyleAttributes, actor: Actor
) -> Style:
    _user_or_mcp(actor)
    style = Style(
        project_id=_open_project(session, project_id),
        name=name.strip(),
        attributes=attributes.model_dump(),
    )
    _created(session, style, actor)
    return style


def create_character(
    session: Session,
    project_id: uuid.UUID,
    name: str,
    description: str,
    attributes: CharacterAttributes,
    actor: Actor,
) -> Character:
    _user_or_mcp(actor)
    character = Character(
        project_id=_open_project(session, project_id),
        name=name.strip(),
        description=description,
        attributes=attributes.model_dump(),
    )
    _created(session, character, actor)
    return character


def _update[Row: (Style, Character)](
    session: Session, row: Row, changes: dict[str, Any], actor: Actor
) -> Row:
    _user_or_mcp(actor)
    if row.archived_at is not None:
        kind = row.__tablename__
        raise DomainError(409, f"{kind.upper()}_ARCHIVED", f"The {kind} is archived.")
    changed = sorted(k for k, v in changes.items() if getattr(row, k) != v)
    if not changed:
        return row
    for key in changed:
        setattr(row, key, changes[key])
    row.version += 1
    _flush_unique(session, row.__tablename__)
    record(
        session,
        actor=actor,
        action=f"{row.__tablename__}.updated",
        subject_type=row.__tablename__,
        subject_id=row.id,
        project_id=row.project_id,
        data={"changed": changed, "version": row.version},
    )
    return row


def update_style(
    session: Session,
    style_id: uuid.UUID,
    actor: Actor,
    *,
    name: str | None = None,
    attributes: StyleAttributes | None = None,
) -> Style:
    changes: dict[str, Any] = {}
    if name is not None:
        changes["name"] = name.strip()
    if attributes is not None:
        changes["attributes"] = attributes.model_dump()
    return _update(session, get_style(session, style_id), changes, actor)


def update_character(
    session: Session,
    character_id: uuid.UUID,
    actor: Actor,
    *,
    name: str | None = None,
    description: str | None = None,
    attributes: CharacterAttributes | None = None,
) -> Character:
    changes: dict[str, Any] = {}
    if name is not None:
        changes["name"] = name.strip()
    if description is not None:
        changes["description"] = description
    if attributes is not None:
        changes["attributes"] = attributes.model_dump()
    return _update(session, get_character(session, character_id), changes, actor)


def set_archived[Row: (Style, Character)](
    session: Session, row: Row, archived: bool, actor: Actor
) -> Row:
    """Archive instead of delete: past generations keep pointing at the row (FR-026)."""
    _user_or_mcp(actor)
    if (row.archived_at is not None) == archived:
        return row
    row.archived_at = utcnow() if archived else None
    # Restoring can clash with a newer row of the same name.
    _flush_unique(session, row.__tablename__)
    record(
        session,
        actor=actor,
        action=f"{row.__tablename__}.{'archived' if archived else 'restored'}",
        subject_type=row.__tablename__,
        subject_id=row.id,
        project_id=row.project_id,
    )
    return row
