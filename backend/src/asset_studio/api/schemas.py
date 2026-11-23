"""API response models."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from asset_studio.modules.projects.config_schema import ProjectConfig


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    name: str
    type: str
    intended_use: str
    mcp_can_decide: bool
    current_config_version: int
    archived_at: datetime | None
    created_at: datetime


class ProjectDetail(ProjectOut):
    config: ProjectConfig


class ConfigVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version: int
    schema_version: int
    created_by_actor: str
    note: str
    created_at: datetime


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    description: str
    config: dict[str, Any]
    assumptions: list[str]
    missing: list[str]
    created_by_actor: str
    project_id: uuid.UUID | None
    created_at: datetime
    problems: list[dict[str, Any]] = []


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    at: datetime
    actor: str
    project_id: uuid.UUID | None
    action: str
    subject_type: str
    subject_id: uuid.UUID | None
    data: dict[str, Any]


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    asset_id: uuid.UUID
    number: int
    state: str
    previous_state: str | None
    sha256: str
    mime: str
    bytes: int
    width: int | None
    height: int | None
    generation_job_id: uuid.UUID | None
    generation_metadata: dict[str, Any]
    first_published_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime


class TransitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    transition_id: str
    from_state: str | None
    to_state: str
    actor: str
    reason: str
    at: datetime


class VersionDetail(VersionOut):
    history: list[TransitionOut]


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    category: str
    slug: str
    name: str
    archived_at: datetime | None
    created_at: datetime


class AssetSummary(AssetOut):
    latest_version: VersionOut | None
    version_count: int


class AssetDetail(AssetOut):
    versions: list[VersionOut]
