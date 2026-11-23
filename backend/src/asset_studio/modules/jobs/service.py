"""Persistent job queue on PostgreSQL (ADR-004): enqueue, claim with leases, progress,
completion, cancellation, retry and recovery after a restart (FR-038, FR-040 to FR-043,
NFR-003). GPU jobs run one at a time across all workers (RULE-012).

States: queued → running → completed | failed | cancelled | interrupted.
Failed, cancelled and interrupted jobs can be retried (back to queued).
"""

import uuid
from datetime import timedelta
from typing import Any, Literal

from sqlalchemy import and_, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from asset_studio.db import utcnow
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.jobs.models import Job, JobEvent, WorkerHeartbeat

Lane = Literal["gpu", "cpu"]
JobState = Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
RETRYABLE = frozenset({"failed", "cancelled", "interrupted"})
# Default lane per kind (Data-Model). Background removal runs as a GPU workflow (D-48).
KIND_LANES: dict[str, Lane] = {
    "generate": "gpu",
    "train": "gpu",
    "remove_background": "gpu",
    "process": "cpu",
    "validate": "cpu",
    "detect_pose": "cpu",
    "export": "cpu",
    "download": "cpu",
    "backup": "cpu",
}
NOTIFY_CHANNEL = "asset_studio_jobs"
GPU_LOCK = "asset_studio_gpu_lane"
DEFAULT_LEASE = timedelta(seconds=60)


def _event(session: Session, job: Job, kind: str, data: dict[str, Any] | None = None) -> None:
    session.add(
        JobEvent(
            job_id=job.id,
            kind=kind,
            data={"state": job.state, "kind": job.kind, "lane": job.lane} | (data or {}),
        )
    )


def _notify(session: Session, lane: str) -> None:
    session.execute(text("SELECT pg_notify(:c, :p)"), {"c": NOTIFY_CHANNEL, "p": lane})


def get_job(session: Session, job_id: uuid.UUID, *, lock: bool = False) -> Job:
    q = select(Job).where(Job.id == job_id).execution_options(populate_existing=True)
    job = session.scalar(q.with_for_update() if lock else q)
    if job is None:
        raise DomainError(404, "JOB_NOT_FOUND", "Job not found.")
    return job


# --- producers and the user -----------------------------------------------------------------


def enqueue(
    session: Session,
    kind: str,
    params: dict[str, Any],
    *,
    actor: Actor,
    project_id: uuid.UUID | None = None,
    lane: Lane | None = None,
    priority: int = 0,
    max_attempts: int = 1,
) -> Job:
    if kind not in KIND_LANES:
        raise DomainError(422, "JOB_KIND_UNKNOWN", f"Unknown job kind: {kind}.")
    job = Job(
        kind=kind,
        lane=lane or KIND_LANES[kind],
        state="queued",
        priority=priority,
        params=params,
        max_attempts=max(1, max_attempts),
        project_id=project_id,
        enqueued_by_actor=actor,
    )
    session.add(job)
    session.flush()
    _event(session, job, "queued", {"actor": actor})
    record(
        session,
        actor=actor,
        action="job.enqueued",
        subject_type="job",
        subject_id=job.id,
        project_id=project_id,
        data={"kind": kind, "lane": job.lane},
    )
    _notify(session, job.lane)
    session.flush()
    return job


def cancel(session: Session, job_id: uuid.UUID, actor: Actor) -> Job:
    """A queued job is cancelled at once; a running one is asked to stop (FR-038)."""
    job = get_job(session, job_id, lock=True)
    if job.state == "queued":
        job.state, job.finished_at, job.wait_reason = "cancelled", utcnow(), None
        _event(session, job, "cancelled", {"actor": actor})
    elif job.state == "running":
        if job.cancel_requested:
            return job
        job.cancel_requested = True
        _event(session, job, "cancel_requested", {"actor": actor})
    else:
        raise DomainError(409, "JOB_NOT_CANCELLABLE", f"A {job.state} job cannot be cancelled.")
    record(
        session,
        actor=actor,
        action="job.cancelled",
        subject_type="job",
        subject_id=job.id,
        project_id=job.project_id,
        data={"state": job.state},
    )
    session.flush()
    return job


def retry(session: Session, job_id: uuid.UUID, actor: Actor) -> Job:
    """Put a failed, cancelled or interrupted job back in the queue (FR-041)."""
    job = get_job(session, job_id, lock=True)
    if job.state not in RETRYABLE:
        raise DomainError(409, "JOB_NOT_RETRYABLE", f"A {job.state} job cannot be retried.")
    previous = job.state
    job.state, job.cancel_requested, job.finished_at = "queued", False, None
    job.locked_by = job.locked_until = None
    job.max_attempts = max(job.max_attempts, job.attempts + 1)
    _event(session, job, "retried", {"actor": actor, "from": previous})
    record(
        session,
        actor=actor,
        action="job.retried",
        subject_type="job",
        subject_id=job.id,
        project_id=job.project_id,
        data={"from": previous},
    )
    _notify(session, job.lane)
    session.flush()
    return job


# --- workers ------------------------------------------------------------------------------


def claim(
    session: Session,
    *,
    lane: Lane,
    worker_id: str,
    kinds: list[str],
    lease: timedelta = DEFAULT_LEASE,
) -> Job | None:
    """Take the next queued job of a lane, or None. Commit right after claiming."""
    if not kinds:
        return None
    if lane == "gpu":
        # Serialise GPU claims across workers, then refuse while a GPU job runs (RULE-012).
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": GPU_LOCK})
        if session.scalar(select(func.count()).where(Job.lane == "gpu", Job.state == "running")):
            return None
    job = session.scalar(
        select(Job)
        .where(Job.lane == lane, Job.state == "queued", Job.kind.in_(kinds))
        .order_by(Job.priority.desc(), Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if job is None:
        return None
    now = utcnow()
    job.state, job.attempts, job.wait_reason, job.error = "running", job.attempts + 1, None, None
    job.locked_by, job.locked_until, job.started_at = worker_id, now + lease, now
    _event(session, job, "started", {"attempt": job.attempts, "worker": worker_id})
    session.flush()
    return job


def _owned(session: Session, job_id: uuid.UUID, worker_id: str) -> Job:
    job = get_job(session, job_id, lock=True)
    if job.state != "running" or job.locked_by != worker_id:
        raise DomainError(409, "JOB_LEASE_LOST", "The job is no longer held by this worker.")
    return job


def report_progress(
    session: Session,
    job_id: uuid.UUID,
    worker_id: str,
    progress: dict[str, Any],
    *,
    lease: timedelta = DEFAULT_LEASE,
) -> bool:
    """Store progress and renew the lease. Returns True when cancellation was requested."""
    job = _owned(session, job_id, worker_id)
    job.progress, job.locked_until = progress, utcnow() + lease
    _event(session, job, "progress", {"progress": progress})
    session.flush()
    return job.cancel_requested


def _finish(session: Session, job: Job, state: str, data: dict[str, Any]) -> Job:
    job.state, job.finished_at = state, utcnow()
    job.locked_by = job.locked_until = None
    _event(session, job, state, data)
    session.flush()
    return job


def complete(
    session: Session, job_id: uuid.UUID, worker_id: str, result: dict[str, Any] | None = None
) -> Job:
    job = _owned(session, job_id, worker_id)
    job.result = result or {}
    return _finish(session, job, "completed", {})


def fail(session: Session, job_id: uuid.UUID, worker_id: str, error: dict[str, Any]) -> Job:
    """Record a failure; requeue while attempts remain, otherwise the job is failed."""
    job = _owned(session, job_id, worker_id)
    job.error = error
    if job.attempts < job.max_attempts:
        job.state, job.locked_by, job.locked_until = "queued", None, None
        _event(session, job, "retry_scheduled", {"error": error, "attempt": job.attempts})
        _notify(session, job.lane)
        session.flush()
        return job
    return _finish(session, job, "failed", {"error": error})


def acknowledge_cancel(session: Session, job_id: uuid.UUID, worker_id: str) -> Job:
    return _finish(session, _owned(session, job_id, worker_id), "cancelled", {})


def recover(session: Session, *, worker_id: str | None = None) -> list[Job]:
    """Mark running jobs interrupted: those whose lease expired or, on shutdown, those held
    by ``worker_id``. Interrupted jobs keep their history and can be retried (NFR-003)."""
    if worker_id is None:
        cond = and_(Job.state == "running", Job.locked_until < utcnow())
    else:
        cond = and_(Job.state == "running", Job.locked_by == worker_id)
    jobs = list(
        session.scalars(
            select(Job)
            .where(cond)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
    )
    for job in jobs:
        _finish(session, job, "interrupted", {"worker": job.locked_by})
    return jobs


def set_wait_reason(session: Session, lane: Lane, reason: str | None) -> int:
    """Explain why queued jobs of a lane do not start (RULE-013); one event per change."""
    jobs = list(
        session.scalars(
            select(Job)
            .where(
                Job.lane == lane,
                Job.state == "queued",
                Job.wait_reason.is_distinct_from(reason),
            )
            .with_for_update(skip_locked=True)
        )
    )
    for job in jobs:
        job.wait_reason = reason
        _event(session, job, "waiting" if reason else "ready", {"reason": reason})
    session.flush()
    return len(jobs)


def touch(
    session: Session, job_ids: list[uuid.UUID], worker_id: str, lease: timedelta = DEFAULT_LEASE
) -> set[uuid.UUID]:
    """Renew the leases of running jobs; returns the ids whose cancellation was requested."""
    if not job_ids:
        return set()
    session.execute(
        update(Job)
        .where(Job.id.in_(job_ids), Job.state == "running", Job.locked_by == worker_id)
        .values(locked_until=utcnow() + lease)
    )
    return set(
        session.scalars(select(Job.id).where(Job.id.in_(job_ids), Job.cancel_requested.is_(True)))
    )


def heartbeat(session: Session, worker_id: str, lanes: list[str], kinds: list[str]) -> None:
    now = utcnow()
    stmt = insert(WorkerHeartbeat).values(
        worker_id=worker_id, lanes=lanes, kinds=kinds, started_at=now, seen_at=now
    )
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=[WorkerHeartbeat.worker_id],
            set_={"seen_at": now, "lanes": lanes, "kinds": kinds},
        )
    )


def remove_heartbeat(session: Session, worker_id: str) -> None:
    session.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id))


# --- readers ------------------------------------------------------------------------------


def list_jobs(
    session: Session,
    *,
    state: str | None = None,
    lane: str | None = None,
    kind: str | None = None,
    project_id: uuid.UUID | None = None,
    before: uuid.UUID | None = None,
    limit: int = 50,
) -> list[Job]:
    """Newest first; ``before`` is a cursor (a job id, time-ordered UUIDv7)."""
    q = select(Job).order_by(Job.id.desc()).limit(limit)
    if state:
        q = q.where(Job.state == state)
    if lane:
        q = q.where(Job.lane == lane)
    if kind:
        q = q.where(Job.kind == kind)
    if project_id:
        q = q.where(Job.project_id == project_id)
    if before:
        q = q.where(Job.id < before)
    return list(session.scalars(q))


def job_events(session: Session, job_id: uuid.UUID) -> list[JobEvent]:
    get_job(session, job_id)
    q = select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.id)
    return list(session.scalars(q))


def events_after(session: Session, after: uuid.UUID | None, limit: int = 200) -> list[JobEvent]:
    """Events in order after a cursor (SSE ``Last-Event-ID``)."""
    q = select(JobEvent).order_by(JobEvent.id).limit(limit)
    if after is not None:
        q = q.where(JobEvent.id > after)
    return list(session.scalars(q))


def summary(
    session: Session, *, worker_timeout: timedelta = timedelta(seconds=30)
) -> dict[str, Any]:
    lanes: dict[str, dict[str, int]] = {"gpu": {}, "cpu": {}}
    for lane, state, n in session.execute(
        select(Job.lane, Job.state, func.count())
        .where(Job.state.in_(("queued", "running")))
        .group_by(Job.lane, Job.state)
    ):
        lanes.setdefault(lane, {})[state] = n
    waiting = {
        lane: reason
        for lane, reason in session.execute(
            select(Job.lane, func.min(Job.wait_reason))
            .where(Job.state == "queued", Job.wait_reason.is_not(None))
            .group_by(Job.lane)
        )
    }
    alive_since = utcnow() - worker_timeout
    workers = [
        {"worker_id": w.worker_id, "lanes": w.lanes, "kinds": w.kinds, "seen_at": w.seen_at}
        for w in session.scalars(
            select(WorkerHeartbeat).where(WorkerHeartbeat.seen_at >= alive_since)
        )
    ]
    return {"lanes": lanes, "wait_reasons": waiting, "workers": workers}
