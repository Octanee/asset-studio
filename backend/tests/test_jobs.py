"""Job queue, worker runtime and events (FR-038, FR-040 to FR-043, RULE-012/013, NFR-003)."""

import uuid
from collections.abc import Callable
from concurrent.futures import Executor, Future
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.errors import DomainError
from asset_studio.modules.jobs import service
from asset_studio.modules.jobs.runner import Handler, JobContext, Runner
from tests.conftest import MCP, ORIGIN, bound_sessions

W = "worker-test"


class InlineExecutor(Executor):
    """Runs submitted work at once on the calling thread (one DB connection in tests)."""

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Future[Any]:
        fut: Future[Any] = Future()
        try:
            fut.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            fut.set_exception(exc)
        return fut


def _runner(connection: Connection, handlers: dict[str, Handler], **kw: Any) -> Runner:
    return Runner(bound_sessions(connection), W, handlers, executor=InlineExecutor(), **kw)


def _state(db: Session, job_id: uuid.UUID) -> str:
    return service.get_job(db, job_id).state


# --- queue semantics ----------------------------------------------------------------------


def test_fr040_enqueue_claim_complete(db: Session) -> None:
    job = service.enqueue(db, "process", {"steps": ["resize"]}, actor="system")
    assert (job.state, job.lane) == ("queued", "cpu")
    claimed = service.claim(db, lane="cpu", worker_id=W, kinds=["process"])
    assert claimed is not None and claimed.id == job.id
    assert (claimed.state, claimed.attempts, claimed.locked_by) == ("running", 1, W)
    service.complete(db, job.id, W, {"ok": True})
    assert [e.kind for e in service.job_events(db, job.id)] == ["queued", "started", "completed"]


def test_unknown_kind_is_rejected(db: Session) -> None:
    with pytest.raises(DomainError) as err:
        service.enqueue(db, "mine-bitcoin", {}, actor="user")
    assert err.value.code == "JOB_KIND_UNKNOWN"


def test_claim_respects_priority_then_age(db: Session) -> None:
    old = service.enqueue(db, "validate", {}, actor="system")
    urgent = service.enqueue(db, "validate", {}, actor="system", priority=5)
    first = service.claim(db, lane="cpu", worker_id=W, kinds=["validate"])
    second = service.claim(db, lane="cpu", worker_id=W, kinds=["validate"])
    assert first is not None and second is not None
    assert (first.id, second.id) == (urgent.id, old.id)


def test_rule012_one_gpu_job_at_a_time(db: Session) -> None:
    a = service.enqueue(db, "generate", {}, actor="user")
    service.enqueue(db, "generate", {}, actor="user")
    assert service.claim(db, lane="gpu", worker_id=W, kinds=["generate"]) is not None
    assert service.claim(db, lane="gpu", worker_id="other", kinds=["generate"]) is None
    service.complete(db, a.id, W)
    assert service.claim(db, lane="gpu", worker_id="other", kinds=["generate"]) is not None


def test_only_the_holder_can_finish_a_job(db: Session) -> None:
    job = service.enqueue(db, "export", {}, actor="user")
    service.claim(db, lane="cpu", worker_id=W, kinds=["export"])
    with pytest.raises(DomainError) as err:
        service.complete(db, job.id, "someone-else")
    assert err.value.code == "JOB_LEASE_LOST"


def test_failure_requeues_while_attempts_remain(db: Session) -> None:
    job = service.enqueue(db, "download", {}, actor="user", max_attempts=2)
    service.claim(db, lane="cpu", worker_id=W, kinds=["download"])
    assert service.fail(db, job.id, W, {"code": "NET"}).state == "queued"
    service.claim(db, lane="cpu", worker_id=W, kinds=["download"])
    failed = service.fail(db, job.id, W, {"code": "NET"})
    assert (failed.state, failed.attempts, failed.error) == ("failed", 2, {"code": "NET"})


def test_nfr003_expired_lease_becomes_interrupted_and_can_be_retried(db: Session) -> None:
    job = service.enqueue(db, "backup", {}, actor="user")
    service.claim(db, lane="cpu", worker_id=W, kinds=["backup"], lease=timedelta(seconds=-1))
    assert [j.id for j in service.recover(db)] == [job.id]
    assert _state(db, job.id) == "interrupted"
    retried = service.retry(db, job.id, "user")
    assert (retried.state, retried.max_attempts) == ("queued", 2)
    assert service.claim(db, lane="cpu", worker_id=W, kinds=["backup"]) is not None


def test_recover_ignores_live_leases(db: Session) -> None:
    service.enqueue(db, "backup", {}, actor="user")
    service.claim(db, lane="cpu", worker_id=W, kinds=["backup"])
    assert service.recover(db) == []


def test_rule013_wait_reason_is_set_and_cleared_once(db: Session) -> None:
    job = service.enqueue(db, "generate", {}, actor="user")
    assert service.set_wait_reason(db, "gpu", "ENGINE_UNAVAILABLE") == 1
    assert service.set_wait_reason(db, "gpu", "ENGINE_UNAVAILABLE") == 0
    assert service.get_job(db, job.id).wait_reason == "ENGINE_UNAVAILABLE"
    assert service.set_wait_reason(db, "gpu", None) == 1
    kinds = [e.kind for e in service.job_events(db, job.id)]
    assert kinds == ["queued", "waiting", "ready"]


# --- worker runtime -----------------------------------------------------------------------


def test_runner_runs_handlers_and_records_progress(connection: Connection, db: Session) -> None:
    job = service.enqueue(db, "process", {"n": 2}, actor="system")
    db.commit()

    def handler(ctx: JobContext) -> dict[str, Any]:
        for i in range(ctx.params["n"]):
            ctx.progress(step=i + 1, of=ctx.params["n"])
        return {"done": True}

    runner = _runner(connection, {"process": handler})
    assert runner.tick() == 1
    final = service.get_job(db, job.id)
    assert final.state == "completed"
    assert (final.result, final.progress) == ({"done": True}, {"step": 2, "of": 2})


def test_runner_records_handler_errors(connection: Connection, db: Session) -> None:
    job = service.enqueue(db, "validate", {}, actor="system")
    db.commit()

    def boom(_: JobContext) -> None:
        raise RuntimeError("bad input")

    _runner(connection, {"validate": boom}).tick()
    final = service.get_job(db, job.id)
    assert final.state == "failed"
    assert final.error == {"code": "RuntimeError", "message": "bad input"}


def test_fr038_cancel_running_job(connection: Connection, db: Session) -> None:
    job = service.enqueue(db, "export", {}, actor="user")
    db.commit()

    def slow(ctx: JobContext) -> None:
        with bound_sessions(connection)() as s, s.begin():
            service.cancel(s, ctx.job_id, "user")  # the user presses Cancel mid-run
        ctx.progress(step=1)

    _runner(connection, {"export": slow}).tick()
    assert _state(db, job.id) == "cancelled"


def test_rule013_closed_gate_holds_gpu_jobs(connection: Connection, db: Session) -> None:
    gpu = service.enqueue(db, "generate", {}, actor="user")
    cpu = service.enqueue(db, "process", {}, actor="user")
    db.commit()
    ran: list[str] = []

    def handle(ctx: JobContext) -> None:
        ran.append(ctx.kind)

    runner = _runner(
        connection,
        {"generate": handle, "process": handle},
        gates={"gpu": lambda: "ENGINE_UNAVAILABLE"},
    )
    runner.tick()
    assert ran == ["process"]
    held = service.get_job(db, gpu.id)
    assert (held.state, held.wait_reason) == ("queued", "ENGINE_UNAVAILABLE")
    assert _state(db, cpu.id) == "completed"


def test_runner_heartbeat_and_stop(connection: Connection, db: Session) -> None:
    runner = _runner(connection, {"process": lambda _: None})
    runner.tick()
    assert [w["worker_id"] for w in service.summary(db)["workers"]] == [W]
    runner.stop(grace=0)
    assert service.summary(db)["workers"] == []


def test_runner_rejects_unknown_kinds(connection: Connection) -> None:
    with pytest.raises(ValueError, match="Unknown job kinds"):
        _runner(connection, {"nope": lambda _: None})


# --- API ----------------------------------------------------------------------------------


def test_jobs_api_list_detail_cancel_retry(client: TestClient, db: Session) -> None:
    job = service.enqueue(db, "generate", {"prompt": "squat"}, actor="mcp")
    db.commit()
    listed = client.get("/api/v1/jobs", params={"state": "queued", "lane": "gpu"}).json()
    assert str(job.id) in [j["id"] for j in listed]

    r = client.post(f"/api/v1/jobs/{job.id}/cancel", headers=ORIGIN)
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    r = client.post(f"/api/v1/jobs/{job.id}/retry", headers=MCP)
    assert r.status_code == 200 and r.json()["state"] == "queued"
    assert [e["kind"] for e in r.json()["events"]] == ["queued", "cancelled", "retried"]
    assert client.post(f"/api/v1/jobs/{job.id}/retry", headers=ORIGIN).status_code == 409


def test_cancel_requires_origin_for_browser_sessions(client: TestClient, db: Session) -> None:
    job = service.enqueue(db, "export", {}, actor="user")
    db.commit()
    assert client.post(f"/api/v1/jobs/{job.id}/cancel").status_code == 403


def test_queue_summary(client: TestClient, db: Session) -> None:
    service.enqueue(db, "generate", {}, actor="user")
    service.set_wait_reason(db, "gpu", "ENGINE_UNAVAILABLE")
    db.commit()
    body = client.get("/api/v1/jobs/summary").json()
    assert body["lanes"]["gpu"]["queued"] >= 1
    assert body["wait_reasons"]["gpu"] == "ENGINE_UNAVAILABLE"


def test_nfr003_events_stream_resumes_from_last_event_id(client: TestClient, db: Session) -> None:
    job = service.enqueue(db, "process", {}, actor="system")
    service.claim(db, lane="cpu", worker_id=W, kinds=["process"])
    db.commit()
    first, second = service.job_events(db, job.id)[:2]

    r = client.get(
        "/api/v1/events", params={"follow": "false"}, headers={"Last-Event-ID": str(first.id)}
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert f"id: {second.id}" in r.text
    assert f"id: {first.id}\n" not in r.text
    assert '"kind":"started"' in r.text


def test_events_need_a_session(anon: TestClient) -> None:
    assert anon.get("/api/v1/events", params={"follow": "false"}).status_code == 401
