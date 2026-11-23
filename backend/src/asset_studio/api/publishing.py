"""Export and publishing API (FR-090 to FR-095, RULE-004, RULE-005)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from asset_studio.api.idempotency import Idem
from asset_studio.api.schemas import (
    ExportRootOut,
    JobOut,
    PlanOut,
    PresetOut,
    PublicationFileOut,
    PublicationOut,
    TargetOut,
)
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.publishing import files
from asset_studio.modules.publishing import service as publishing
from asset_studio.modules.publishing.models import ExportTarget
from asset_studio.modules.publishing.presets import PresetDefinition

roots_router = APIRouter()
project_router = APIRouter()
presets_router = APIRouter()
targets_router = APIRouter()
router = APIRouter()
Db = Annotated[Session, Depends(get_session)]


class PresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    definition: PresetDefinition = Field(default_factory=PresetDefinition)


class TargetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    root_id: str = Field(max_length=10)
    subdir: str = Field(default="", max_length=300)


class PlanRequest(BaseModel):
    """What to publish: chosen versions, a collection, or the whole project (FR-092)."""

    project_id: uuid.UUID
    preset_id: uuid.UUID
    target_id: uuid.UUID
    version_ids: list[uuid.UUID] | None = Field(default=None, max_length=2000)
    collection_id: uuid.UUID | None = None
    whole_project: bool = False

    @model_validator(mode="after")
    def _one_source(self) -> "PlanRequest":
        chosen = [bool(self.version_ids), self.collection_id is not None, self.whole_project]
        if sum(chosen) != 1:
            raise ValueError("choose versions, a collection or the whole project")
        return self


class PublishRequest(BaseModel):
    plan_id: uuid.UUID
    # RULE-004: each existing file is confirmed by its path; nothing is overwritten otherwise.
    confirm_overwrites: list[str] = Field(default_factory=list, max_length=20000)


def _target(t: ExportTarget) -> TargetOut:
    name = publishing.root_name(t)
    return TargetOut(
        id=t.id,
        project_id=t.project_id,
        name=t.name,
        root_name=name,
        subdir=t.subdir,
        available=name is not None,
        archived_at=t.archived_at,
        created_at=t.created_at,
    )


def _plan(view: publishing.PlanView) -> PlanOut:
    p = view.plan
    return PlanOut(
        id=p.id,
        project_id=p.project_id,
        preset_id=p.preset_id,
        target_id=p.target_id,
        items=p.items,  # type: ignore[arg-type]
        skipped=p.skipped,
        files=view.file_count,
        overwrites=view.overwrites,
        created_at=p.created_at,
        used_at=p.used_at,
        job_id=p.job_id,
    )


@roots_router.get("", response_model=list[ExportRootOut])
def list_roots(_: CurrentActor) -> list[ExportRootOut]:
    """The export folders the containers can write to (ADR-013)."""
    return [ExportRootOut(id=r.id, name=r.name) for r in files.roots()]


@project_router.get("/{project_id}/presets", response_model=list[PresetOut])
def list_presets(
    db: Db, _: CurrentActor, project_id: uuid.UUID, include_archived: bool = False
) -> list[Any]:
    return publishing.list_presets(db, project_id, include_archived)


@project_router.post("/{project_id}/presets", response_model=PresetOut, status_code=201)
def create_preset(db: Db, actor: CurrentActor, project_id: uuid.UUID, body: PresetRequest) -> Any:
    return publishing.save_preset(
        db, name=body.name, definition=body.definition, actor=actor, project_id=project_id
    )


@presets_router.put("/{preset_id}", response_model=PresetOut)
def update_preset(db: Db, actor: CurrentActor, preset_id: uuid.UUID, body: PresetRequest) -> Any:
    return publishing.save_preset(
        db, name=body.name, definition=body.definition, actor=actor, preset_id=preset_id
    )


@presets_router.post("/{preset_id}/archive", response_model=PresetOut)
def archive_preset(db: Db, actor: CurrentActor, preset_id: uuid.UUID) -> Any:
    return publishing.archive_preset(db, preset_id, True, actor)


@presets_router.post("/{preset_id}/restore", response_model=PresetOut)
def restore_preset(db: Db, actor: CurrentActor, preset_id: uuid.UUID) -> Any:
    return publishing.archive_preset(db, preset_id, False, actor)


@project_router.get("/{project_id}/targets", response_model=list[TargetOut])
def list_targets(
    db: Db, _: CurrentActor, project_id: uuid.UUID, include_archived: bool = False
) -> list[TargetOut]:
    return [_target(t) for t in publishing.list_targets(db, project_id, include_archived)]


@project_router.post("/{project_id}/targets", response_model=TargetOut, status_code=201)
def create_target(
    db: Db, actor: CurrentActor, project_id: uuid.UUID, body: TargetRequest
) -> TargetOut:
    return _target(
        publishing.create_target(db, project_id, body.name, body.root_id, body.subdir, actor)
    )


@targets_router.post("/{target_id}/archive", response_model=TargetOut)
def archive_target(db: Db, actor: CurrentActor, target_id: uuid.UUID) -> TargetOut:
    return _target(publishing.archive_target(db, target_id, True, actor))


@targets_router.post("/{target_id}/restore", response_model=TargetOut)
def restore_target(db: Db, actor: CurrentActor, target_id: uuid.UUID) -> TargetOut:
    return _target(publishing.archive_target(db, target_id, False, actor))


@router.post(":plan", response_model=PlanOut, status_code=201)
def plan_publication(db: Db, actor: CurrentActor, body: PlanRequest) -> PlanOut:
    """The files a publish would write, with the ones that already exist (DD-006)."""
    return _plan(
        publishing.plan(
            db,
            body.project_id,
            preset_id=body.preset_id,
            target_id=body.target_id,
            actor=actor,
            version_ids=body.version_ids,
            collection_id=body.collection_id,
        )
    )


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(db: Db, _: CurrentActor, plan_id: uuid.UUID) -> PlanOut:
    return _plan(publishing.get_plan(db, plan_id))


@router.post("", response_model=JobOut, status_code=202)
def publish(db: Db, actor: CurrentActor, idem: Idem, body: PublishRequest) -> Any:
    """Publish a plan. Existing files need ``confirm_overwrites`` (RULE-004); Claude may
    publish only where the project allows it and never overwrites (RULE-005)."""
    return idem.run(
        JobOut,
        202,
        body,
        lambda: publishing.publish(db, body.plan_id, body.confirm_overwrites, actor),
    )


def _publications(rows: list[Any]) -> list[PublicationOut]:
    return [
        PublicationOut.model_validate(p).model_copy(
            update={"files": [PublicationFileOut.model_validate(f) for f in fs]}
        )
        for p, fs in rows
    ]


@router.get("", response_model=list[PublicationOut])
def list_publications(
    db: Db,
    _: CurrentActor,
    project_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[PublicationOut]:
    """Publications, newest first: version, preset, target, file hashes, time (FR-093)."""
    return _publications(
        publishing.list_publications(
            db, project_id=project_id, asset_id=asset_id, version_id=version_id, limit=limit
        )
    )


@router.get("/current", response_model=list[PublicationOut])
def current_publications(db: Db, _: CurrentActor, asset_id: uuid.UUID) -> list[PublicationOut]:
    """What each target currently holds for the asset (FR-093)."""
    return [PublicationOut.model_validate(p) for p in publishing.current_for_asset(db, asset_id)]
