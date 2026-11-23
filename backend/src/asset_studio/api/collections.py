"""Collections API (FR-056): named groups of a project's assets, changed by the user."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from asset_studio.api.schemas import CollectionOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.assets import collections as service

project_router = APIRouter()
router = APIRouter()
Db = Annotated[Session, Depends(get_session)]


class CollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CollectionAssets(BaseModel):
    asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


def _out(r: service.CollectionRow) -> CollectionOut:
    c = r.collection
    return CollectionOut(
        id=c.id,
        project_id=c.project_id,
        name=c.name,
        created_at=c.created_at,
        asset_count=r.asset_count,
    )


@project_router.get("/{project_id}/collections", response_model=list[CollectionOut])
def list_collections(db: Db, _: CurrentActor, project_id: uuid.UUID) -> list[CollectionOut]:
    return [_out(r) for r in service.list_collections(db, project_id)]


@project_router.post("/{project_id}/collections", response_model=CollectionOut, status_code=201)
def create_collection(
    db: Db, actor: CurrentActor, project_id: uuid.UUID, body: CollectionRequest
) -> CollectionOut:
    c = service.create_collection(db, project_id, body.name, actor)
    return _out(service.row(db, c))


@router.patch("/{collection_id}", response_model=CollectionOut)
def rename_collection(
    db: Db, actor: CurrentActor, collection_id: uuid.UUID, body: CollectionRequest
) -> CollectionOut:
    return _out(service.row(db, service.rename_collection(db, collection_id, body.name, actor)))


@router.delete("/{collection_id}", status_code=204)
def delete_collection(db: Db, actor: CurrentActor, collection_id: uuid.UUID) -> Response:
    """Remove the collection; its assets are not changed."""
    service.delete_collection(db, collection_id, actor)
    return Response(status_code=204)


@router.post("/{collection_id}/assets", response_model=CollectionOut)
def add_assets(
    db: Db, actor: CurrentActor, collection_id: uuid.UUID, body: CollectionAssets
) -> CollectionOut:
    return _out(service.add_assets(db, collection_id, body.asset_ids, actor))


@router.delete("/{collection_id}/assets/{asset_id}", response_model=CollectionOut)
def remove_asset(
    db: Db, actor: CurrentActor, collection_id: uuid.UUID, asset_id: uuid.UUID
) -> CollectionOut:
    return _out(service.remove_asset(db, collection_id, asset_id, actor))
