"""Generation API (FR-030-FR-038, FR-052, RULE-007, RULE-013, RULE-015)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from asset_studio.api.idempotency import Idem
from asset_studio.api.schemas import JobOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.generation import service
from asset_studio.modules.generation.service import GenerationSpec
from asset_studio.modules.providers.engine import EngineMonitor, get_engine_monitor

router = APIRouter()
versions_router = APIRouter()
Db = Annotated[Session, Depends(get_session)]
Engine = Annotated[EngineMonitor, Depends(get_engine_monitor)]


class Problem(BaseModel):
    code: str
    model_id: str | None
    detail: str


class WorkflowRef(BaseModel):
    id: str
    version: int


class EngineState(BaseModel):
    available: bool
    reason: str | None


class GenerationCheckOut(BaseModel):
    ready: bool
    problems: list[Problem]
    # Models whose licence the user still has to confirm for this project (RULE-007).
    licence_confirmation_required: list[str]
    workflow: WorkflowRef
    models: dict[str, str]
    prompts: list[str]
    negative: str
    jobs: int
    # GPU jobs wait while the engine is down; queueing still works (RULE-013).
    engine: EngineState


class QueuedOut(BaseModel):
    asset_ids: list[uuid.UUID]
    jobs: list[JobOut]


@router.post(":check", response_model=GenerationCheckOut)
def check(db: Db, _: CurrentActor, engine: Engine, spec: GenerationSpec) -> GenerationCheckOut:
    p = service.plan(db, spec)
    health = engine.health()
    return GenerationCheckOut(
        ready=not p.problems and not p.licence_pending,
        problems=[Problem(**x) for x in p.problems],
        licence_confirmation_required=p.licence_pending,
        workflow=WorkflowRef(**p.frozen["workflow"]),
        models={role: m.id for role, m in p.models.items()},
        prompts=p.positive,
        negative=p.negative,
        jobs=len(p.targets) * spec.variants,
        engine=EngineState(available=health.available, reason=health.reason),
    )


@router.post("", response_model=QueuedOut, status_code=202)
def generate(db: Db, actor: CurrentActor, idem: Idem, spec: GenerationSpec) -> Any:
    def work() -> QueuedOut:
        q = service.queue(db, spec, actor)
        return QueuedOut(asset_ids=q.asset_ids, jobs=[JobOut.model_validate(j) for j in q.jobs])

    return idem.run(QueuedOut, 202, spec, work)


@versions_router.post("/{version_id}:regenerate", response_model=QueuedOut, status_code=202)
def regenerate(
    db: Db,
    actor: CurrentActor,
    idem: Idem,
    version_id: uuid.UUID,
    changes: Annotated[dict[str, Any], Body(description="Fields of the request to change.")],
) -> Any:
    def work() -> QueuedOut:
        q = service.regenerate(db, version_id, changes, actor)
        return QueuedOut(asset_ids=q.asset_ids, jobs=[JobOut.model_validate(j) for j in q.jobs])

    return idem.run(QueuedOut, 202, (str(version_id), sorted(changes.items())), work)
