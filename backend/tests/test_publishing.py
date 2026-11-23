"""Export presets, targets and publishing (FR-090 to FR-095, RULE-004, RULE-005, AC-003,
AC-004, ADR-013)."""

import io
import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.config import get_settings
from asset_studio.modules.assets import service as assets
from asset_studio.modules.assets.models import AssetVersion
from asset_studio.modules.projects.config_schema import ProjectConfig
from asset_studio.modules.projects.service import create_project
from asset_studio.modules.publishing import service as publishing
from asset_studio.modules.publishing.presets import PresetDefinition, Size, file_paths
from asset_studio.modules.storage.local import LocalStorage
from tests.conftest import MCP, ORIGIN, project_config
from tests.test_jobs import _runner


@pytest.fixture
def exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "exports"
    root.mkdir()
    monkeypatch.setenv("ASSET_STUDIO_EXPORT_ROOTS", str(root))
    get_settings.cache_clear()
    yield root.resolve()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _storage(storage: LocalStorage, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publishing, "get_storage", lambda: storage)


def _png(colour: tuple[int, int, int] = (20, 40, 160)) -> bytes:
    out = io.BytesIO()
    image = Image.new("RGB", (128, 128), (255, 255, 255))
    image.paste(colour, (32, 32, 96, 96))
    image.save(out, "PNG")
    return out.getvalue()


def _project(db: Session, name: str = "Exerzio illustrations") -> uuid.UUID:
    return create_project(db, ProjectConfig.model_validate(project_config(name=name)), "user").id


STEPS = {
    "generated": [],
    "awaiting_review": ["start_processing", "processing_succeeded"],
    "approved": ["start_processing", "processing_succeeded", "approve"],
}


def _version(
    db: Session, storage: LocalStorage, pid: uuid.UUID, name: str, *, state: str = "approved"
) -> AssetVersion:
    asset = assets.create_asset(db, pid, category="lower-body", name=name, actor="system")
    v = assets.add_version(
        db,
        storage,
        asset.id,
        io.BytesIO(_png()),
        mime="image/png",
        actor="system",
        generation_metadata={"prompt": "a squat", "seed": 7, "pose": {"view": "Front"}},
    )
    for action in STEPS[state]:
        assets.transition(db, v.id, action, "user" if action == "approve" else "system")
    return v


def _setup(client: TestClient, pid: uuid.UUID, **definition: Any) -> tuple[str, str]:
    body = {
        "name": "Web",
        "definition": {"format": "png", "sizes": [{"width": 64, "height": 64}], **definition},
    }
    r = client.post(f"/api/v1/projects/{pid}/presets", json=body, headers=ORIGIN)
    assert r.status_code == 201, r.text
    preset = r.json()["id"]
    r = client.post(
        f"/api/v1/projects/{pid}/targets",
        json={"name": "App assets", "root_id": "0", "subdir": "app/images"},
        headers=ORIGIN,
    )
    assert r.status_code == 201, r.text
    return preset, r.json()["id"]


def _plan(
    client: TestClient,
    pid: uuid.UUID,
    preset: str,
    target: str,
    headers: dict[str, str] = ORIGIN,
    **kw: Any,
) -> Any:
    body = {"project_id": str(pid), "preset_id": preset, "target_id": target, **kw}
    return client.post("/api/v1/publications:plan", json=body, headers=headers)


def _publish(
    client: TestClient,
    plan: dict[str, Any],
    headers: dict[str, str] = ORIGIN,
    confirm: bool = False,
) -> Any:
    body = {"plan_id": plan["id"], "confirm_overwrites": plan["overwrites"] if confirm else []}
    return client.post("/api/v1/publications", json=body, headers=headers)


def _run(connection: Connection) -> None:
    runner = _runner(connection, publishing.HANDLERS)
    while runner.tick():
        pass


# --- presets (FR-090) -------------------------------------------------------------------------


def test_fr090_preset_patterns_are_checked() -> None:
    with pytest.raises(ValidationError, match="unknown placeholders"):
        PresetDefinition(naming="{asset}-{colour}")
    with pytest.raises(ValidationError, match="'\\.\\.'"):
        PresetDefinition(folders="{category}/../up")
    with pytest.raises(ValidationError, match="reserved"):
        PresetDefinition(naming="a:b")
    with pytest.raises(ValidationError, match="own suffix"):
        PresetDefinition(sizes=[Size(width=64, height=64), Size(width=32, height=32)])
    with pytest.raises(ValidationError, match="needs"):
        PresetDefinition(
            naming="{asset}",
            sizes=[Size(width=64, height=64), Size(suffix="sm", width=32, height=32)],
        )


def test_fr090_values_cannot_leave_the_folder() -> None:
    d = PresetDefinition(
        format="jpeg",
        folders="{category}/{view}",
        naming="{asset}{suffix}-{size}",
        sizes=[Size(width=64, height=64), Size(suffix="sm", width=32, height=32)],
    )
    values = {"asset": "squat", "category": "../..", "view": "Front/x"}
    assert [p for _, p in file_paths(d, values)] == [
        "x/front-x/squat-64x64.jpg",
        "x/front-x/squat-sm-32x32.jpg",
    ]


# --- targets (FR-091, ADR-013) ----------------------------------------------------------------


def test_fr091_targets_stay_under_an_export_root(
    client: TestClient, db: Session, exports: Path
) -> None:
    pid = _project(db)
    assert client.get("/api/v1/export-roots").json() == [{"id": "0", "name": "exports"}]
    url = f"/api/v1/projects/{pid}/targets"

    def create(headers: dict[str, str] = ORIGIN, **body: str) -> Any:
        return client.post(url, json={"name": "x", "root_id": "0", **body}, headers=headers).json()

    assert create(root_id="9")["code"] == "EXPORT_ROOT_UNKNOWN"
    assert create(subdir="a/../../b")["code"] == "TARGET_PATH_INVALID"
    assert create(subdir="C:/x")["code"] == "TARGET_PATH_INVALID"
    assert create(headers=MCP)["code"] == "ACTOR_NOT_ALLOWED"
    made = create(name="App", subdir="./app//img/")
    assert (made["subdir"], made["root_name"], made["available"]) == ("app/img", "exports", True)


# --- publishing (FR-092, FR-093) --------------------------------------------------------------


def test_fr092_fr093_publish_writes_files_and_records_them(
    client: TestClient,
    db: Session,
    storage: LocalStorage,
    connection: Connection,
    exports: Path,
) -> None:
    pid = _project(db)
    v = _version(db, storage, pid, "Squat")
    waiting = _version(db, storage, pid, "Lunge", state="awaiting_review")
    preset, target = _setup(client, pid, metadata="sidecar", folders="{category}")
    r = _plan(client, pid, preset, target, version_ids=[str(v.id), str(waiting.id)])
    assert r.status_code == 201, r.text
    plan = r.json()
    assert [f["path"] for f in plan["items"][0]["files"]] == [
        "lower-body/squat-front.png",
        "lower-body/squat-front.json",
    ]
    assert (plan["overwrites"], plan["files"]) == ([], 2)
    assert plan["skipped"][0]["reason"] == "NOT_APPROVED"

    r = _publish(client, plan)
    assert r.status_code == 202, r.text
    assert (r.json()["kind"], r.json()["lane"]) == ("export", "cpu")
    _run(connection)

    out = exports / "app/images/lower-body"
    assert Image.open(out / "squat-front.png").size == (64, 64)
    sidecar = json.loads((out / "squat-front.json").read_text(encoding="utf-8"))
    assert (sidecar["asset"], sidecar["version"], sidecar["seed"]) == ("squat", 1, 7)
    assert str(exports) not in json.dumps(sidecar)  # no machine paths in published files

    version = client.get(f"/api/v1/versions/{v.id}").json()
    assert version["state"] == "published" and version["first_published_at"]
    assert version["history"][-1]["transition_id"] == "T-09"
    pubs = client.get("/api/v1/publications", params={"version_id": str(v.id)}).json()
    assert len(pubs) == 1
    files = {f["relative_path"]: f for f in pubs[0]["files"]}
    assert files["lower-body/squat-front.png"]["overwrote_sha256"] is None
    current = client.get("/api/v1/publications/current", params={"asset_id": str(v.asset_id)})
    assert [p["id"] for p in current.json()] == [pubs[0]["id"]]
    assert _publish(client, plan).json()["code"] == "PLAN_USED"


def test_rule004_ac003_overwrites_need_confirmation_and_are_audited(
    client: TestClient,
    db: Session,
    storage: LocalStorage,
    connection: Connection,
    exports: Path,
) -> None:
    pid = _project(db)
    v = _version(db, storage, pid, "Squat")
    preset, target = _setup(client, pid)
    existing = exports / "app/images/squat-front.png"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old file")

    plan = _plan(client, pid, preset, target, version_ids=[str(v.id)]).json()
    assert plan["overwrites"] == ["squat-front.png"]
    r = _publish(client, plan)
    assert r.status_code == 409
    assert (r.json()["code"], r.json()["paths"]) == ("OVERWRITE_NOT_CONFIRMED", ["squat-front.png"])
    assert existing.read_bytes() == b"old file"

    assert _publish(client, plan, confirm=True).status_code == 202
    _run(connection)
    assert existing.read_bytes() != b"old file"
    pub = client.get("/api/v1/publications", params={"version_id": str(v.id)}).json()[0]
    f = pub["files"][0]
    assert f["confirmed_overwrite"] and f["overwrote_sha256"]
    trail = client.get("/api/v1/audit", params={"action": "publication.file_overwritten"}).json()
    assert trail[0]["data"]["path"] == "squat-front.png"
    assert trail[0]["data"]["previous_sha256"] == f["overwrote_sha256"]

    # Publishing the same version to the target again is T-10.
    plan = _plan(client, pid, preset, target, version_ids=[str(v.id)]).json()
    assert _publish(client, plan, confirm=True).status_code == 202
    _run(connection)
    history = client.get(f"/api/v1/versions/{v.id}").json()["history"]
    assert history[-1]["transition_id"] == "T-10"


def test_rule004_a_file_that_appears_after_planning_is_never_overwritten(
    client: TestClient,
    db: Session,
    storage: LocalStorage,
    connection: Connection,
    exports: Path,
) -> None:
    pid = _project(db)
    v = _version(db, storage, pid, "Squat")
    preset, target = _setup(client, pid)
    plan = _plan(client, pid, preset, target, version_ids=[str(v.id)]).json()
    assert _publish(client, plan).status_code == 202
    late = exports / "app/images/squat-front.png"
    late.parent.mkdir(parents=True)
    late.write_bytes(b"someone else's file")
    _run(connection)
    assert late.read_bytes() == b"someone else's file"
    assert client.get(f"/api/v1/versions/{v.id}").json()["state"] == "approved"


def test_rule005_ac004_claude_publishes_only_when_allowed_and_never_overwrites(
    client: TestClient,
    db: Session,
    storage: LocalStorage,
    connection: Connection,
    exports: Path,
) -> None:
    pid = _project(db)
    v = _version(db, storage, pid, "Squat")
    preset, target = _setup(client, pid)
    r = _plan(client, pid, preset, target, MCP, version_ids=[str(v.id)])
    assert (r.status_code, r.json()["code"]) == (403, "MCP_NOT_ALLOWED")

    client.patch(f"/api/v1/projects/{pid}/settings", json={"mcp_can_decide": True}, headers=ORIGIN)
    plan = _plan(client, pid, preset, target, MCP, version_ids=[str(v.id)]).json()
    assert _publish(client, plan).json()["code"] == "PLAN_OTHER_ACTOR"
    r = _publish(client, plan, MCP)
    assert r.status_code == 202, r.text
    _run(connection)
    assert client.get(f"/api/v1/versions/{v.id}").json()["history"][-1]["actor"] == "mcp"

    # Publishing again (T-10) is the user's decision.
    r = _plan(client, pid, preset, target, MCP, version_ids=[str(v.id)])
    assert r.json()["code"] == "NOTHING_TO_PUBLISH"
    other = _version(db, storage, pid, "Squat 2")
    (exports / "app/images/squat-2-front.png").write_bytes(b"x")
    plan = _plan(client, pid, preset, target, MCP, version_ids=[str(other.id)]).json()
    assert _publish(client, plan, MCP, confirm=True).json()["code"] == "MCP_OVERWRITE_NOT_ALLOWED"


def test_fr092_whole_project_and_collections(
    client: TestClient,
    db: Session,
    storage: LocalStorage,
    exports: Path,
) -> None:
    pid = _project(db)
    squat = _version(db, storage, pid, "Squat")
    assets.add_version(  # a newer, not yet approved version: v1 is the one to publish
        db,
        storage,
        squat.asset_id,
        io.BytesIO(_png((200, 0, 0))),
        mime="image/png",
        actor="system",
    )
    _version(db, storage, pid, "Plank", state="awaiting_review")
    lunge = _version(db, storage, pid, "Lunge")
    preset, target = _setup(client, pid)

    plan = _plan(client, pid, preset, target, whole_project=True).json()
    assert sorted((i["asset"], i["number"]) for i in plan["items"]) == [("Lunge", 1), ("Squat", 1)]
    assert [s["asset"] for s in plan["skipped"]] == ["Plank"]

    cid = client.post(
        f"/api/v1/projects/{pid}/collections", json={"name": "Legs"}, headers=ORIGIN
    ).json()["id"]
    client.post(
        f"/api/v1/collections/{cid}/assets",
        json={"asset_ids": [str(lunge.asset_id)]},
        headers=ORIGIN,
    )
    plan = _plan(client, pid, preset, target, collection_id=cid).json()
    assert [i["asset"] for i in plan["items"]] == ["Lunge"]
    r = _plan(client, pid, preset, target, whole_project=True, collection_id=cid)
    assert r.status_code == 422


def test_plan_refuses_two_versions_writing_one_file(
    client: TestClient, db: Session, storage: LocalStorage, exports: Path
) -> None:
    pid = _project(db)
    a = _version(db, storage, pid, "Squat")
    b = _version(db, storage, pid, "Lunge")
    preset, target = _setup(client, pid, naming="{category}")
    r = _plan(client, pid, preset, target, version_ids=[str(a.id), str(b.id)])
    assert (r.status_code, r.json()["code"]) == (409, "PLAN_PATH_COLLISION")
