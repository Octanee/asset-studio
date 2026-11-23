"""API response models."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class ProcessedFile(BaseModel):
    sha256: str
    mime: str
    bytes: int
    width: int
    height: int


class ProcessingFailure(BaseModel):
    code: str
    message: str
    step: str | None = None
    job_id: str | None = None


class ProcessingOut(BaseModel):
    """Post-processing of a version (FR-065); storage keys stay on the server."""

    steps: list[dict[str, Any]] = Field(default_factory=list)
    output: ProcessedFile | None = None
    error: ProcessingFailure | None = None
    background_removed: bool = False
    finished_at: str | None = None


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
    processing: ProcessingOut = Field(default_factory=ProcessingOut)

    @field_validator("processing", mode="before")
    @classmethod
    def _processing(cls, value: Any) -> Any:
        if isinstance(value, dict) and "cutout" in value:  # the stored record, not a dump
            return {**value, "background_removed": bool(value["cutout"])}
        return value


class RuleResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rule: str
    status: str
    details: dict[str, Any]


class ValidationOut(BaseModel):
    """The newest technical validation run of a version (FR-060). Informative (RULE-009)."""

    run_id: uuid.UUID | None
    checked_at: datetime | None
    summary: dict[str, int]
    results: list[RuleResultOut]


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


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    lane: str
    state: str
    priority: int
    params: dict[str, Any]
    result: dict[str, Any]
    progress: dict[str, Any]
    error: dict[str, Any] | None
    wait_reason: str | None
    attempts: int
    max_attempts: int
    cancel_requested: bool
    project_id: uuid.UUID | None
    enqueued_by_actor: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    at: datetime
    kind: str
    data: dict[str, Any]


class JobDetail(JobOut):
    events: list[JobEventOut]


class QueueSummary(BaseModel):
    lanes: dict[str, dict[str, int]]
    wait_reasons: dict[str, str]
    workers: list[dict[str, Any]]
