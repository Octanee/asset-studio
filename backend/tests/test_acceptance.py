"""Acceptance journeys (WP-18): AC-001, AC-005, AC-006, AC-012, AC-013 and AC-015 end to end
through the API, with the fake engine. The other criteria have their own tests (see the
Acceptance-Coverage page in the docs): AC-002 `test_ac002_*`, AC-003 `test_rule004_*`,
AC-004 `test_ac004_*`, AC-007 `test_fr072_fr075_*` + `test_fr073_*` + `test_lora_generation`,
AC-008 `test_ac008_*`, AC-009 `test_ac009_*`, AC-010 `test_ac010_*`, AC-011 `test_ac011_*`,
AC-014 `i18n.test.tsx` and `Shell.test.tsx`."""

import json
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.config import Settings
from asset_studio.modules.assets.lifecycle import TRANSITIONS
from asset_studio.modules.generation import service as generation
from asset_studio.modules.poses.builtin import BUILTIN_POSES
from asset_studio.modules.processing import service as processing
from asset_studio.modules.providers.fake import FakeProvider
from asset_studio.modules.publishing import service as publishing
from asset_studio.modules.storage.local import LocalStorage, get_storage
from asset_studio.modules.svg import service as svg
from tests.conftest import MCP, ORIGIN, bound_sessions
from tests.test_generation import (  # noqa: F401 - fixtures used by name
    _project,
    _spec,
    _style_character,
    api,
    engine,
    installed,
)
from tests.test_jobs import _runner
from tests.test_publishing import (  # noqa: F401 - the exports fixture is used by name
    _plan,
    _publish,
    _setup,
    exports,
)
from tests.test_publishing import _run as _run_exports

ROOT = Path(__file__).resolve().parents[2]
EXERCISES = [
    "Squat", "Lunge", "Plank", "Push-up", "Glute bridge",
    "Jumping jacks", "Side plank", "Calf raise", "Mountain climber", "Bird dog",
]  # fmt: skip


@pytest.fixture(autouse=True)
def _storage(storage: LocalStorage, monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (processing, publishing, svg):
        monkeypatch.setattr(module, "get_storage", lambda: storage)


def _work(connection: Connection, **gates: Any) -> None:
    """Run the queue until nothing more can start (generation, processing, SVG)."""
    handlers = {"generate": generation.handle_generate, **processing.HANDLERS, **svg.HANDLERS}
    runner = _runner(connection, handlers, gates=gates or None)
    while runner.tick():
        pass


def _act(client: TestClient, version_id: str, action: str, **extra: Any) -> Any:
    return client.post(
        f"/api/v1/versions/{version_id}/transitions",
        json={"action": action, **extra},
        headers=ORIGIN,
    )


def _poses(client: TestClient, pid: str, n: int) -> list[str]:
    """The built-in poses, then the user's own poses from the editor up to ``n``."""
    ids = [str(p.id) for p in BUILTIN_POSES]
    for i in range(n - len(ids)):
        base = BUILTIN_POSES[i % len(BUILTIN_POSES)].keypoints
        shift = 0.02 * (i + 1)
        moved = [[min(0.95, p[0] + shift), p[1], p[2]] if p else None for p in base]
        r = client.post(
            f"/api/v1/projects/{pid}/poses",
            json={"name": f"{EXERCISES[len(ids)]} pose", "view": "left", "keypoints": moved},
            headers=ORIGIN,
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids[:n]


def _version_of(client: TestClient, asset_id: str) -> dict[str, Any]:
    (version,) = client.get(f"/api/v1/assets/{asset_id}/versions").json()
    return dict(version)


# --- AC-001 -----------------------------------------------------------------------------------


def test_ac001_ten_exercises_with_one_style_and_character_are_approved_and_exported(
    api: TestClient, engine: FakeProvider, connection: Connection, exports: Path
) -> None:
    pid = _project(api)
    style, character = _style_character(api, pid)
    poses = _poses(api, pid, len(EXERCISES))
    asset_ids = []
    for name, pose in zip(EXERCISES, poses, strict=True):
        body = _spec(
            pid,
            asset={"category": "core", "name": name},
            prompt=f"doing a {name.lower()}",
            style_id=style,
            character_id=character,
            pose_id=pose,
        )
        r = api.post("/api/v1/generations", json=body, headers=ORIGIN)
        assert r.status_code == 202, r.text
        asset_ids += r.json()["asset_ids"]
    _work(connection)

    versions = [_version_of(api, a) for a in asset_ids]
    assert [v["state"] for v in versions] == ["awaiting_review"] * len(EXERCISES)
    for v, pose in zip(versions, poses, strict=True):
        meta = v["generation_metadata"]
        assert meta["style"]["id"] == style and meta["character"]["id"] == character
        assert meta["pose"]["id"] == pose  # each exercise its own pose
    for v in versions:
        assert _act(api, v["id"], "approve").json()["state"] == "approved"

    preset, target = _setup(api, uuid.UUID(pid))
    plan = _plan(api, uuid.UUID(pid), preset, target, whole_project=True).json()
    assert len(plan["items"]) == len(EXERCISES) and not plan["overwrites"]
    assert _publish(api, plan).status_code == 202
    _run_exports(connection)
    assert len(list(exports.rglob("*.png"))) == len(EXERCISES)
    assert {_version_of(api, a)["state"] for a in asset_ids} == {"published"}


# --- AC-012 and AC-013 on a version that was really exported -------------------------------


def test_ac012_ac013_a_published_version_keeps_its_approval_and_is_deleted_only_when_archived(
    api: TestClient, engine: FakeProvider, connection: Connection, exports: Path
) -> None:
    pid = _project(api)
    ids = []
    for name in ("Squat", "Plank"):
        body = _spec(pid, asset={"category": "core", "name": name})
        ids += api.post("/api/v1/generations", json=body, headers=ORIGIN).json()["asset_ids"]
    _work(connection)
    published, unpublished = (_version_of(api, a)["id"] for a in ids)
    for v in (published, unpublished):
        _act(api, v, "approve")
    preset, target = _setup(api, uuid.UUID(pid))
    plan = _plan(api, uuid.UUID(pid), preset, target, version_ids=[published]).json()
    _publish(api, plan)
    _run_exports(connection)

    # AC-012: no withdrawal once published; a reason is required before that.
    assert _act(api, published, "withdraw", reason="wrong pose").status_code == 409
    r = _act(api, unpublished, "withdraw")
    assert r.status_code == 422 and r.json()["code"] == "REASON_REQUIRED"
    withdrawn = _act(api, unpublished, "withdraw", reason="wrong pose").json()
    assert withdrawn["state"] == "awaiting_review"

    # AC-013: archive first, then delete; the audit entry stays.
    confirm = {"confirm": published}
    r = api.delete(f"/api/v1/versions/{published}", params=confirm, headers=ORIGIN)
    assert r.status_code == 409
    assert _act(api, published, "archive").json()["state"] == "archived"
    r = api.delete(f"/api/v1/versions/{published}", params=confirm, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["state"] == "deleted"
    audit = api.get("/api/v1/audit", params={"action": "asset_version.deleted"}).json()
    assert [e["subject_id"] for e in audit] == [published]
    history = api.get(f"/api/v1/versions/{published}").json()["history"]
    assert [h["to_state"] for h in history][-3:] == ["published", "archived", "deleted"]


# --- AC-005 -----------------------------------------------------------------------------------


@contextmanager
def _restarted(connection: Connection, storage: LocalStorage) -> Iterator[TestClient]:
    """A new API process on the same database: nothing survives in memory."""
    from asset_studio.db import get_session, get_sessionmaker
    from asset_studio.main import create_app

    app = create_app()
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_sessionmaker] = lambda: bound_sessions(connection)

    def _session() -> Iterator[Session]:
        with bound_sessions(connection)() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/api/v1/session").status_code == 200
        yield c


def test_ac005_job_history_and_queued_jobs_survive_a_restart(
    api: TestClient, engine: FakeProvider, connection: Connection, storage: LocalStorage
) -> None:
    pid = _project(api)
    first = api.post("/api/v1/generations", json=_spec(pid), headers=ORIGIN).json()
    # That job runs; two more are queued; then the backend and the worker stop.
    _runner(connection, {"generate": generation.handle_generate}).tick()
    more = api.post("/api/v1/generations", json=_spec(pid, variants=2), headers=ORIGIN).json()
    jobs = [j["id"] for j in first["jobs"] + more["jobs"]]
    before = {j: api.get(f"/api/v1/jobs/{j}").json()["state"] for j in jobs}
    assert sorted(before.values()) == ["completed", "queued", "queued"]

    with _restarted(connection, storage) as again:
        after = {j: again.get(f"/api/v1/jobs/{j}").json() for j in jobs}
        assert {j: a["state"] for j, a in after.items()} == before
        done = next(a for a in after.values() if a["state"] == "completed")
        kinds = [e["kind"] for e in done["events"]]
        assert kinds[:2] == ["queued", "started"] and kinds[-1] == "completed"
        # A new worker picks up the queued jobs.
        _work(connection)
        assert {again.get(f"/api/v1/jobs/{j}").json()["state"] for j in jobs} == {"completed"}


# --- AC-006 -----------------------------------------------------------------------------------


def test_ac006_with_the_engine_stopped_everything_but_generation_works(
    api: TestClient, engine: FakeProvider, connection: Connection, exports: Path
) -> None:
    pid = _project(api)
    engine.available = False
    check = api.post("/api/v1/generations:check", json=_spec(pid), headers=ORIGIN).json()
    assert check["engine"] == {"available": False, "reason": "ENGINE_UNAVAILABLE"}
    held = api.post("/api/v1/generations", json=_spec(pid), headers=ORIGIN).json()["jobs"][0]
    svg_body = {
        "project_id": pid,
        "template_id": "icon-line",
        "asset": {"category": "core", "name": "Icon"},
    }
    asset_id = api.post("/api/v1/svg", json=svg_body, headers=ORIGIN).json()["asset_id"]
    _work(connection, gpu=lambda: "ENGINE_UNAVAILABLE")

    job = api.get(f"/api/v1/jobs/{held['id']}").json()
    assert job["state"] == "queued" and job["wait_reason"] == "ENGINE_UNAVAILABLE"
    library = api.get("/api/v1/assets", params={"project_id": pid}).json()
    assert "Icon" in {a["name"] for a in library}
    version = _version_of(api, asset_id)
    assert version["state"] == "awaiting_review"  # SVG and processing ran on the CPU
    assert _act(api, version["id"], "approve").json()["state"] == "approved"  # review
    preset, target = _setup(api, uuid.UUID(pid))
    plan = _plan(api, uuid.UUID(pid), preset, target, version_ids=[version["id"]]).json()
    assert _publish(api, plan).status_code == 202
    _run_exports(connection)
    assert len(list(exports.rglob("*.png"))) == 1  # export


# --- failure scenario: the engine fails, the user retries --------------------------------------


def test_an_engine_failure_keeps_the_approved_version_and_a_retry_succeeds(
    api: TestClient, engine: FakeProvider, connection: Connection
) -> None:
    pid = _project(api)
    asset_id = api.post("/api/v1/generations", json=_spec(pid), headers=ORIGIN).json()["asset_ids"][
        0
    ]
    _work(connection)
    approved = _version_of(api, asset_id)
    _act(api, approved["id"], "approve")

    engine.fail_with = "CUDA out of memory"
    body = _spec(pid, asset={"asset_id": asset_id})
    job = api.post("/api/v1/generations", json=body, headers=ORIGIN).json()["jobs"][0]
    _work(connection)
    failed = api.get(f"/api/v1/jobs/{job['id']}").json()
    assert (failed["state"], failed["error"]["code"]) == ("failed", "GENERATION_FAILED")
    versions = api.get(f"/api/v1/assets/{asset_id}/versions").json()
    assert [(v["number"], v["state"]) for v in versions] == [(1, "approved")]  # untouched

    engine.fail_with = None
    assert api.post(f"/api/v1/jobs/{job['id']}/retry", headers=ORIGIN).status_code == 200
    _work(connection)
    assert api.get(f"/api/v1/jobs/{job['id']}").json()["state"] == "completed"
    versions = api.get(f"/api/v1/assets/{asset_id}/versions").json()
    states = sorted((v["number"], v["state"]) for v in versions)
    assert states == [(1, "approved"), (2, "awaiting_review")]


# --- AC-015 -----------------------------------------------------------------------------------


def test_ac015_nothing_listens_outside_loopback(client: TestClient) -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    lines = [line.strip() for line in compose.splitlines()]
    ports = [line for line in lines if line.startswith('- "') and "_PORT:-" in line]
    assert len(ports) == 4  # db, api, mcp, web
    assert all(p.startswith('- "127.0.0.1:') for p in ports), ports
    assert Settings().host == "127.0.0.1"
    # Requests that name another host are refused even on loopback (DNS rebinding).
    r = client.get("/api/v1/system/health", headers={"Host": "attacker.example"})
    assert r.status_code == 400
    r = client.post("/api/v1/projects", json={}, headers={"Origin": "http://attacker.example"})
    assert r.status_code == 403
    assert client.get("/api/v1/projects", headers=MCP).status_code == 200


# --- AC-014: every audit action has a label in both languages ------------------------------------

# Actions built at run time, and what they expand to. A new f-string action must be added here,
# so it cannot reach the activity feed without a label.
DYNAMIC_ACTIONS = {
    "asset_version.{action}": {f"asset_version.{a}" for a in TRANSITIONS},
    "engine.{action}": {f"engine.{a}" for a in ("start", "stop", "restart")},
    "pose.{'archived' if archived else 'restored'}": {"pose.archived", "pose.restored"},
    "reference.{'archived' if archived else 'restored'}": {
        "reference.archived",
        "reference.restored",
    },
    "{row.__tablename__}.created": {"style.created", "character.created"},
    "{row.__tablename__}.updated": {"style.updated", "character.updated"},
    "{row.__tablename__}.{'archived' if archived else 'restored'}": {
        f"{t}.{s}" for t in ("style", "character") for s in ("archived", "restored")
    },
    "{target_type}.lora_linked": {"style.lora_linked", "character.lora_linked"},
    "{target_type}.lora_unlinked": {"style.lora_unlinked", "character.lora_unlinked"},
}


def _audit_actions() -> set[str]:
    source = "\n".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "backend/src/asset_studio").rglob("*.py")
    )
    actions = set(re.findall(r'action="([a-z_]+\.[a-z_]+)"', source))
    for first, second in re.findall(
        r'"([a-z_]+\.[a-z_]+)" if [^\n]* else "([a-z_]+\.[a-z_]+)"', source
    ):
        actions |= {first, second}
    dynamic = set(re.findall(r'action=f"([^"]+)"', source))
    assert dynamic == set(DYNAMIC_ACTIONS), "a new run-time audit action needs a label"
    for expanded in DYNAMIC_ACTIONS.values():
        actions |= expanded
    return actions


@pytest.mark.parametrize("lang", ["en", "pl"])
def test_ac014_every_audit_action_has_a_label(lang: str) -> None:
    path = ROOT / f"frontend/src/i18n/{lang}.json"
    labels = json.loads(path.read_text(encoding="utf-8"))["asset"]["actions"]
    actions = _audit_actions()
    assert len(actions) > 80
    missing = sorted(a for a in actions if a.replace(".", "_") not in labels)
    assert missing == []
