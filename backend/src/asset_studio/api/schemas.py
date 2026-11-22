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
