"""Projects API (FR-001 to FR-008)."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from asset_studio.api.schemas import ConfigVersionOut, DraftOut, ProjectDetail, ProjectOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.projects import service
from asset_studio.modules.projects.config_schema import ProjectConfig

router = APIRouter()
Db = Annotated[Session, Depends(get_session)]


def _detail(session: Session, project_id: uuid.UUID) -> ProjectDetail:
    project = service.get_project(session, project_id)
    return ProjectDetail(
        **ProjectOut.model_validate(project).model_dump(),
        config=service.current_config(session, project),
    )


class ConfigUpdate(BaseModel):
    config: ProjectConfig
    acknowledge_breaking: bool = False
    note: str = Field(default="", max_length=500)


class SettingsUpdate(BaseModel):
    mcp_can_decide: bool


class CloneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class DraftCreate(BaseModel):
    description: str = Field(default="", max_length=4000)
    config: dict[str, Any]
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    missing: list[str] = Field(default_factory=list, max_length=50)


class DraftConfirm(BaseModel):
    config: ProjectConfig


class DraftUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=4000)
    config: dict[str, Any] | None = None
    assumptions: list[str] | None = Field(default=None, max_length=50)
    missing: list[str] | None = Field(default=None, max_length=50)


class ConfigCheck(BaseModel):
    config: dict[str, Any]


class ConfigProblems(BaseModel):
    valid: bool
    problems: list[dict[str, Any]]


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Db, _: CurrentActor, include_archived: bool = False) -> list[Any]:
    return service.list_projects(db, include_archived)


@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(db: Db, actor: CurrentActor, config: ProjectConfig) -> ProjectDetail:
    project = service.create_project(db, config, actor)
    return _detail(db, project.id)


@router.post("/import", response_model=ProjectDetail, status_code=201)
def import_project(
    db: Db, actor: CurrentActor, document: Annotated[dict[str, Any], Body()]
) -> ProjectDetail:
    project = service.import_document(db, document, actor)
    return _detail(db, project.id)


@router.post("/drafts", response_model=DraftOut, status_code=201)
def create_draft(db: Db, actor: CurrentActor, body: DraftCreate) -> DraftOut:
    draft, problems = service.create_draft(
        db,
        description=body.description,
        config=body.config,
        assumptions=body.assumptions,
        missing=body.missing,
        actor=actor,
    )
    return DraftOut(
        **DraftOut.model_validate(draft).model_dump(exclude={"problems"}), problems=problems
    )


@router.get("/drafts", response_model=list[DraftOut])
def list_drafts(
    db: Db, _: CurrentActor, status: Literal["pending", "confirmed", "discarded"] | None = "pending"
) -> list[DraftOut]:
    return [_draft(d) for d in service.list_drafts(db, status)]


@router.post("/drafts/{draft_id}/discard", response_model=DraftOut)
def discard_draft(db: Db, actor: CurrentActor, draft_id: uuid.UUID) -> DraftOut:
    """User only: turn down a draft (RULE-010)."""
    return _draft(service.discard_draft(db, draft_id, actor))


def _draft(draft: Any) -> DraftOut:
    return DraftOut(
        **DraftOut.model_validate(draft).model_dump(exclude={"problems"}),
        problems=service.draft_problems(draft),
    )


@router.post(":validate", response_model=ConfigProblems)
def validate_config(_: CurrentActor, body: ConfigCheck) -> ConfigProblems:
    """Check a configuration against the schema without saving it."""
    problems = service.config_problems(body.config)
    return ConfigProblems(valid=not problems, problems=problems)


@router.put("/drafts/{draft_id}", response_model=DraftOut)
def update_draft(db: Db, actor: CurrentActor, draft_id: uuid.UUID, body: DraftUpdate) -> DraftOut:
    draft = service.update_draft(
        db,
        draft_id,
        actor=actor,
        description=body.description,
        config=body.config,
        assumptions=body.assumptions,
        missing=body.missing,
    )
    return DraftOut(
        **DraftOut.model_validate(draft).model_dump(exclude={"problems"}),
        problems=service.draft_problems(draft),
    )


@router.get("/drafts/{draft_id}", response_model=DraftOut)
def get_draft(db: Db, _: CurrentActor, draft_id: uuid.UUID) -> DraftOut:
    draft = service.get_draft(db, draft_id)
    return DraftOut(
        **DraftOut.model_validate(draft).model_dump(exclude={"problems"}),
        problems=service.draft_problems(draft),
    )


@router.post("/drafts/{draft_id}/confirm", response_model=ProjectDetail, status_code=201)
def confirm_draft(
    db: Db, actor: CurrentActor, draft_id: uuid.UUID, body: DraftConfirm
) -> ProjectDetail:
    project = service.confirm_draft(db, draft_id, body.config, actor)
    return _detail(db, project.id)


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(db: Db, _: CurrentActor, project_id: uuid.UUID) -> ProjectDetail:
    return _detail(db, project_id)


@router.put("/{project_id}/config", response_model=ProjectDetail)
def update_config(
    db: Db, actor: CurrentActor, project_id: uuid.UUID, body: ConfigUpdate
) -> ProjectDetail:
    service.update_config(
        db,
        project_id,
        body.config,
        actor,
        acknowledge_breaking=body.acknowledge_breaking,
        note=body.note,
    )
    return _detail(db, project_id)


@router.patch("/{project_id}/settings", response_model=ProjectOut)
def update_settings(
    db: Db, actor: CurrentActor, project_id: uuid.UUID, body: SettingsUpdate
) -> Any:
    return service.set_mcp_can_decide(db, project_id, body.mcp_can_decide, actor)


@router.post("/{project_id}/archive", response_model=ProjectOut)
def archive(db: Db, actor: CurrentActor, project_id: uuid.UUID) -> Any:
    return service.set_archived(db, project_id, True, actor)


@router.post("/{project_id}/restore", response_model=ProjectOut)
def restore(db: Db, actor: CurrentActor, project_id: uuid.UUID) -> Any:
    return service.set_archived(db, project_id, False, actor)


@router.post("/{project_id}/clone", response_model=ProjectDetail, status_code=201)
def clone(db: Db, actor: CurrentActor, project_id: uuid.UUID, body: CloneRequest) -> ProjectDetail:
    project = service.clone_project(db, project_id, body.name, actor)
    return _detail(db, project.id)


@router.get("/{project_id}/config/versions", response_model=list[ConfigVersionOut])
def versions(db: Db, _: CurrentActor, project_id: uuid.UUID) -> list[Any]:
    return service.config_versions(db, project_id)


@router.get("/{project_id}/config/export")
def export_config(db: Db, _: CurrentActor, project_id: uuid.UUID) -> dict[str, Any]:
    return service.export_document(db, project_id)
