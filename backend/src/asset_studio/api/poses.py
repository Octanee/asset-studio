"""Poses API (FR-020 to FR-022): the library, the editor's saves, and detection jobs."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from asset_studio.api.idempotency import Idem
from asset_studio.api.schemas import JobOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.poses import service
from asset_studio.modules.poses.skeleton import Keypoints

project_router = APIRouter()
router = APIRouter()
Db = Annotated[Session, Depends(get_session)]
View = Literal["front", "back", "left", "right", "three_quarter", "other"]
Aspect = Annotated[float, Field(gt=0.2, lt=5)]
Name = Annotated[str, Field(min_length=1, max_length=120, pattern=r"\S")]
Unit = Annotated[float, Field(ge=0, le=1)]


class PoseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID | None
    name: str
    view: str
    aspect: float
    keypoints: list[tuple[float, float, float] | None]
    source: str
    source_reference_id: uuid.UUID | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PoseCreate(BaseModel):
    name: Name
    view: View = "front"
    aspect: Aspect = 0.75
    keypoints: Keypoints
    source_reference_id: uuid.UUID | None = None


class PoseUpdate(BaseModel):
    name: Name | None = None
    view: View | None = None
    aspect: Aspect | None = None
    keypoints: Keypoints | None = None


class DetectRequest(BaseModel):
    reference_id: uuid.UUID
    # A box drawn by the user when the person detector misses the figure (WP-01 spike).
    box: tuple[Unit, Unit, Unit, Unit] | None = None


@router.get("", response_model=list[PoseOut])
def list_poses(
    db: Db,
    _: CurrentActor,
    project_id: uuid.UUID | None = None,
    view: View | None = None,
    include_archived: bool = False,
) -> list[Any]:
    return service.list_poses(db, project_id, view=view, include_archived=include_archived)


@router.post(":detect", response_model=JobOut, status_code=202)
def detect_pose(db: Db, actor: CurrentActor, idem: Idem, body: DetectRequest) -> Any:
    return idem.run(
        JobOut,
        202,
        body,
        lambda: service.request_detection(db, body.reference_id, actor, box=body.box),
    )


@project_router.post("/{project_id}/poses", response_model=PoseOut, status_code=201)
def create_pose(db: Db, actor: CurrentActor, project_id: uuid.UUID, body: PoseCreate) -> Any:
    return service.create_pose(
        db,
        project_id,
        name=body.name,
        view=body.view,
        aspect=body.aspect,
        keypoints=body.keypoints,
        actor=actor,
        source_reference_id=body.source_reference_id,
    )


@router.get("/{pose_id}", response_model=PoseOut)
def get_pose(db: Db, _: CurrentActor, pose_id: uuid.UUID) -> Any:
    return service.get_pose(db, pose_id)


@router.patch("/{pose_id}", response_model=PoseOut)
def update_pose(db: Db, actor: CurrentActor, pose_id: uuid.UUID, body: PoseUpdate) -> Any:
    return service.update_pose(
        db,
        pose_id,
        actor,
        name=body.name,
        view=body.view,
        aspect=body.aspect,
        keypoints=body.keypoints,
    )


@router.post("/{pose_id}/archive", response_model=PoseOut)
def archive_pose(db: Db, actor: CurrentActor, pose_id: uuid.UUID) -> Any:
    return service.set_archived(db, pose_id, True, actor)


@router.post("/{pose_id}/restore", response_model=PoseOut)
def restore_pose(db: Db, actor: CurrentActor, pose_id: uuid.UUID) -> Any:
    return service.set_archived(db, pose_id, False, actor)
