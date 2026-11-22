"""Jobs API and the live event stream (FR-038, FR-040, FR-041, NFR-003).

Jobs are enqueued by the modules that own the work (generation, processing, ...); there is
no generic "run any job" endpoint.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from asset_studio.api.schemas import JobDetail, JobEventOut, JobOut, QueueSummary
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session, get_sessionmaker
from asset_studio.modules.jobs import service
from asset_studio.modules.jobs.service import JobState, Lane

jobs_router = APIRouter()
events_router = APIRouter()
Db = Annotated[Session, Depends(get_session)]
POLL_SECONDS = 1.0
KEEPALIVE_SECONDS = 15.0
BATCH = 200


def _detail(db: Session, job_id: uuid.UUID) -> JobDetail:
    job = service.get_job(db, job_id)
    return JobDetail(
        **JobOut.model_validate(job).model_dump(),
        events=[JobEventOut.model_validate(e) for e in service.job_events(db, job_id)],
    )


@jobs_router.get("", response_model=list[JobOut])
def list_jobs(
    db: Db,
    _: CurrentActor,
    state: JobState | None = None,
    lane: Lane | None = None,
    kind: Annotated[str | None, Query(max_length=32)] = None,
    project_id: uuid.UUID | None = None,
    before: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Any]:
    return service.list_jobs(
        db, state=state, lane=lane, kind=kind, project_id=project_id, before=before, limit=limit
    )


@jobs_router.get("/summary", response_model=QueueSummary)
def queue_summary(db: Db, _: CurrentActor) -> dict[str, Any]:
    return service.summary(db)


@jobs_router.get("/{job_id}", response_model=JobDetail)
def get_job(db: Db, _: CurrentActor, job_id: uuid.UUID) -> JobDetail:
    return _detail(db, job_id)


@jobs_router.post("/{job_id}/cancel", response_model=JobDetail)
def cancel_job(db: Db, actor: CurrentActor, job_id: uuid.UUID) -> JobDetail:
    service.cancel(db, job_id, actor)
    return _detail(db, job_id)


@jobs_router.post("/{job_id}/retry", response_model=JobDetail)
def retry_job(db: Db, actor: CurrentActor, job_id: uuid.UUID) -> JobDetail:
    service.retry(db, job_id, actor)
    return _detail(db, job_id)


def _read(factory: sessionmaker[Session], after: uuid.UUID | None) -> list[JobEventOut]:
    with factory() as s:
        return [JobEventOut.model_validate(e) for e in service.events_after(s, after, BATCH)]


def _frame(event: JobEventOut) -> str:
    payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
    return f"id: {event.id}\nevent: job\ndata: {payload}\n\n"


@events_router.get("")
async def events(
    request: Request,
    _: CurrentActor,
    factory: Annotated[sessionmaker[Session], Depends(get_sessionmaker)],
    last_event_id: Annotated[uuid.UUID | None, Header()] = None,
    after: uuid.UUID | None = None,
    follow: bool = True,
) -> StreamingResponse:
    """Server-Sent Events. A reconnecting client sends ``Last-Event-ID`` and receives what it
    missed, because events are stored (NFR-003). ``follow=false`` returns the backlog only."""
    cursor = last_event_id or after

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor
        yield "retry: 3000\n\n"
        idle = 0.0
        while True:
            batch = await run_in_threadpool(_read, factory, cursor)
            for event in batch:
                cursor = event.id
                yield _frame(event)
            if len(batch) == BATCH:
                continue
            if not follow or await request.is_disconnected():
                return
            await asyncio.sleep(POLL_SECONDS)
            idle = 0.0 if batch else idle + POLL_SECONDS
            if idle >= KEEPALIVE_SECONDS:
                idle = 0.0
                yield ": keepalive\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
