"""Worker runtime: one GPU lane (a single job at a time) and a CPU pool.

Handlers are registered per job kind by the modules that own the work (generation,
processing, ...). A lane gate reports why a lane cannot run, e.g. the engine is down;
its jobs then wait in the queue with that reason (RULE-013).
"""

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy.orm import Session, sessionmaker

from asset_studio.errors import DomainError
from asset_studio.modules.jobs import service
from asset_studio.modules.jobs.service import GATE_EXEMPT, KIND_LANES, PAUSE_EXEMPT, Lane

log = structlog.get_logger("worker")


class JobCancelled(Exception):
    """Raised inside a handler when the user cancelled the running job."""


class WorkerStopping(Exception):
    """Raised inside a handler when the worker shuts down; the job becomes interrupted."""


@dataclass
class JobContext:
    job_id: uuid.UUID
    kind: str
    params: dict[str, Any]
    runner: "Runner"
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def progress(self, **data: Any) -> None:
        """Report progress; raises if the job was cancelled or the worker is stopping."""
        with self.runner.sessions() as s, s.begin():
            if service.report_progress(
                s, self.job_id, self.runner.worker_id, data, lease=self.runner.lease
            ):
                self.cancel_event.set()
        self.check()

    def check(self) -> None:
        if self.runner.stopping.is_set():
            raise WorkerStopping
        if self.cancel_event.is_set():
            raise JobCancelled


Handler = Callable[[JobContext], dict[str, Any] | None]
Gate = Callable[[], str | None]


class Runner:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        worker_id: str,
        handlers: dict[str, Handler],
        *,
        gates: dict[Lane, Gate] | None = None,
        paused: Callable[[Session], bool] | None = None,
        cpu_slots: int = 2,
        lease: timedelta = service.DEFAULT_LEASE,
        executor: Executor | None = None,
    ) -> None:
        unknown = set(handlers) - set(KIND_LANES)
        if unknown:
            raise ValueError(f"Unknown job kinds: {sorted(unknown)}")
        self.sessions, self.worker_id, self.handlers = sessions, worker_id, handlers
        self.gates = gates or {}
        # Is the whole queue paused (a setting owned by the system module, read each tick)?
        self.paused = paused
        self.lease = lease
        self.slots: dict[Lane, int] = {"gpu": 1, "cpu": cpu_slots}
        self.pool = executor or ThreadPoolExecutor(
            max_workers=1 + cpu_slots, thread_name_prefix="job"
        )
        self.running: dict[uuid.UUID, tuple[Lane, JobContext, Future[None]]] = {}
        self.stopping = threading.Event()
        self._lock = threading.Lock()

    def kinds(self, lane: Lane) -> list[str]:
        return sorted(k for k in self.handlers if KIND_LANES[k] == lane)

    @property
    def lanes(self) -> list[Lane]:
        return [lane for lane in ("gpu", "cpu") if self.kinds(lane)]

    def start(self) -> None:
        """On start, jobs left running by a stopped or crashed worker become interrupted."""
        with self.sessions() as s, s.begin():
            for job in service.recover(s):
                log.warning("job.interrupted", job_id=str(job.id), kind=job.kind)

    def tick(self) -> int:
        """One scheduling round: heartbeat, recovery, leases, gates and claims.
        Returns the number of jobs started."""
        with self._lock:
            for jid in [j for j, (_, _, fut) in self.running.items() if fut.done()]:
                del self.running[jid]
            ids = list(self.running)
        with self.sessions() as s, s.begin():
            service.heartbeat(s, self.worker_id, list(self.lanes), sorted(self.handlers))
            service.recover(s)
            cancelled = service.touch(s, ids, self.worker_id, self.lease)
            paused = self.paused(s) if self.paused else False
        with self._lock:
            for jid in cancelled & set(self.running):
                self.running[jid][1].cancel_event.set()
        started = 0
        for lane in self.lanes:
            kinds = self.kinds(lane)
            if paused:  # only backup and restore start while the queue is paused
                reason: str | None = "QUEUE_PAUSED"
                kinds = [k for k in kinds if k in PAUSE_EXEMPT]
            else:
                reason = self.gates[lane]() if lane in self.gates else None
                if reason:  # only kinds that do not need the engine may start
                    kinds = [k for k in kinds if k in GATE_EXEMPT]
            with self.sessions() as s, s.begin():
                service.set_wait_reason(s, lane, reason)
            if not kinds:
                continue
            while (
                not self.stopping.is_set() and self._free(lane) and self._claim_and_run(lane, kinds)
            ):
                started += 1
        return started

    def _free(self, lane: Lane) -> bool:
        with self._lock:
            busy = sum(1 for ln, _, fut in self.running.values() if ln == lane and not fut.done())
        return busy < self.slots[lane]

    def _claim_and_run(self, lane: Lane, kinds: list[str]) -> bool:
        with self.sessions() as s, s.begin():
            job = service.claim(
                s, lane=lane, worker_id=self.worker_id, kinds=kinds, lease=self.lease
            )
            if job is None:
                return False
            ctx = JobContext(job_id=job.id, kind=job.kind, params=dict(job.params), runner=self)
        log.info("job.started", job_id=str(ctx.job_id), kind=ctx.kind, lane=lane)
        with self._lock:
            self.running[ctx.job_id] = (lane, ctx, self.pool.submit(self._execute, ctx))
        return True

    def _execute(self, ctx: JobContext) -> None:
        try:
            try:
                result = self.handlers[ctx.kind](ctx)
            except WorkerStopping:
                return  # left running; stop() marks it interrupted
            except JobCancelled:
                with self.sessions() as s, s.begin():
                    service.acknowledge_cancel(s, ctx.job_id, self.worker_id)
                log.info("job.cancelled", job_id=str(ctx.job_id))
                return
            except Exception as exc:  # the handler failed: record it, keep the worker alive
                log.warning("job.failed", job_id=str(ctx.job_id), error=type(exc).__name__)
                error = {
                    "code": str(getattr(exc, "code", type(exc).__name__)),
                    "message": str(exc)[:500],
                }
                with self.sessions() as s, s.begin():
                    service.fail(s, ctx.job_id, self.worker_id, error)
                return
            with self.sessions() as s, s.begin():
                service.complete(s, ctx.job_id, self.worker_id, result or {})
            log.info("job.completed", job_id=str(ctx.job_id))
        except DomainError as exc:  # lease lost: the job was marked interrupted meanwhile
            log.warning("job.lease_lost", job_id=str(ctx.job_id), code=exc.code)

    def wait_idle(self, timeout: float | None = None) -> None:
        with self._lock:
            futures = [fut for _, _, fut in self.running.values()]
        for fut in futures:
            fut.result(timeout=timeout)

    def stop(self, grace: float = 10.0) -> None:
        """Stop claiming, give handlers a moment, then mark this worker's jobs interrupted."""
        self.stopping.set()
        try:
            self.wait_idle(timeout=grace)
        except TimeoutError:
            log.warning("worker.stop_timeout", running=len(self.running))
        self.pool.shutdown(wait=False, cancel_futures=True)
        with self.sessions() as s, s.begin():
            for job in service.recover(s, worker_id=self.worker_id):
                log.warning("job.interrupted", job_id=str(job.id), kind=job.kind)
            service.remove_heartbeat(s, self.worker_id)
