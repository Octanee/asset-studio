"""Styles and characters API (FR-010, FR-011, FR-015)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.styles import loras, service
from asset_studio.modules.styles.service import CharacterAttributes, StyleAttributes

project_router = APIRouter()
styles_router = APIRouter()
characters_router = APIRouter()
Db = Annotated[Session, Depends(get_session)]
Name = Annotated[str, Field(min_length=1, max_length=120, pattern=r"\S")]


class StyleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    attributes: StyleAttributes
    version: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CharacterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    attributes: CharacterAttributes
    version: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StyleCreate(BaseModel):
    name: Name
    attributes: StyleAttributes = Field(default_factory=StyleAttributes)


class StyleUpdate(BaseModel):
    name: Name | None = None
    attributes: StyleAttributes | None = None


class CharacterCreate(BaseModel):
    name: Name
    description: str = Field(default="", max_length=4000)
    attributes: CharacterAttributes = Field(default_factory=CharacterAttributes)


class CharacterUpdate(BaseModel):
    name: Name | None = None
    description: str | None = Field(default=None, max_length=4000)
    attributes: CharacterAttributes | None = None


@project_router.get("/{project_id}/styles", response_model=list[StyleOut])
def list_styles(
    db: Db, _: CurrentActor, project_id: uuid.UUID, include_archived: bool = False
) -> list[Any]:
    return service.list_styles(db, project_id, include_archived)


@project_router.post("/{project_id}/styles", response_model=StyleOut, status_code=201)
def create_style(db: Db, actor: CurrentActor, project_id: uuid.UUID, body: StyleCreate) -> Any:
    return service.create_style(db, project_id, body.name, body.attributes, actor)


@project_router.get("/{project_id}/characters", response_model=list[CharacterOut])
def list_characters(
    db: Db, _: CurrentActor, project_id: uuid.UUID, include_archived: bool = False
) -> list[Any]:
    return service.list_characters(db, project_id, include_archived)


@project_router.post("/{project_id}/characters", response_model=CharacterOut, status_code=201)
def create_character(
    db: Db, actor: CurrentActor, project_id: uuid.UUID, body: CharacterCreate
) -> Any:
    return service.create_character(
        db, project_id, body.name, body.description, body.attributes, actor
    )


@styles_router.get("/{style_id}", response_model=StyleOut)
def get_style(db: Db, _: CurrentActor, style_id: uuid.UUID) -> Any:
    return service.get_style(db, style_id)


@styles_router.patch("/{style_id}", response_model=StyleOut)
def update_style(db: Db, actor: CurrentActor, style_id: uuid.UUID, body: StyleUpdate) -> Any:
    return service.update_style(db, style_id, actor, name=body.name, attributes=body.attributes)


@styles_router.post("/{style_id}/archive", response_model=StyleOut)
def archive_style(db: Db, actor: CurrentActor, style_id: uuid.UUID) -> Any:
    return service.set_archived(db, service.get_style(db, style_id), True, actor)


@styles_router.post("/{style_id}/restore", response_model=StyleOut)
def restore_style(db: Db, actor: CurrentActor, style_id: uuid.UUID) -> Any:
    return service.set_archived(db, service.get_style(db, style_id), False, actor)


@characters_router.get("/{character_id}", response_model=CharacterOut)
def get_character(db: Db, _: CurrentActor, character_id: uuid.UUID) -> Any:
    return service.get_character(db, character_id)


@characters_router.patch("/{character_id}", response_model=CharacterOut)
def update_character(
    db: Db, actor: CurrentActor, character_id: uuid.UUID, body: CharacterUpdate
) -> Any:
    return service.update_character(
        db,
        character_id,
        actor,
        name=body.name,
        description=body.description,
        attributes=body.attributes,
    )


@characters_router.post("/{character_id}/archive", response_model=CharacterOut)
def archive_character(db: Db, actor: CurrentActor, character_id: uuid.UUID) -> Any:
    return service.set_archived(db, service.get_character(db, character_id), True, actor)


@characters_router.post("/{character_id}/restore", response_model=CharacterOut)
def restore_character(db: Db, actor: CurrentActor, character_id: uuid.UUID) -> Any:
    return service.set_archived(db, service.get_character(db, character_id), False, actor)


# --- LoRA links (FR-016, FR-075) ---------------------------------------------------------------


class LoraLinkOut(BaseModel):
    model_id: str
    name: str
    family_id: str | None
    status: str
    strength: float
    trigger_word: str | None


class LoraLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strength: float = Field(default=0.8, ge=0, le=2)


@styles_router.get("/{style_id}/loras", response_model=list[LoraLinkOut])
def style_loras(db: Db, _: CurrentActor, style_id: uuid.UUID) -> list[dict[str, Any]]:
    return loras.list_links(db, "style", style_id)


@styles_router.put("/{style_id}/loras/{model_id}", response_model=list[LoraLinkOut])
def link_style_lora(
    db: Db, actor: CurrentActor, style_id: uuid.UUID, model_id: str, body: LoraLinkIn
) -> list[dict[str, Any]]:
    return loras.link(db, "style", style_id, model_id, body.strength, actor)


@styles_router.delete("/{style_id}/loras/{model_id}", response_model=list[LoraLinkOut])
def unlink_style_lora(
    db: Db, actor: CurrentActor, style_id: uuid.UUID, model_id: str
) -> list[dict[str, Any]]:
    return loras.unlink(db, "style", style_id, model_id, actor)


@characters_router.get("/{character_id}/loras", response_model=list[LoraLinkOut])
def character_loras(db: Db, _: CurrentActor, character_id: uuid.UUID) -> list[dict[str, Any]]:
    return loras.list_links(db, "character", character_id)


@characters_router.put("/{character_id}/loras/{model_id}", response_model=list[LoraLinkOut])
def link_character_lora(
    db: Db, actor: CurrentActor, character_id: uuid.UUID, model_id: str, body: LoraLinkIn
) -> list[dict[str, Any]]:
    return loras.link(db, "character", character_id, model_id, body.strength, actor)


@characters_router.delete("/{character_id}/loras/{model_id}", response_model=list[LoraLinkOut])
def unlink_character_lora(
    db: Db, actor: CurrentActor, character_id: uuid.UUID, model_id: str
) -> list[dict[str, Any]]:
    return loras.unlink(db, "character", character_id, model_id, actor)
