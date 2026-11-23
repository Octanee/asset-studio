"""Generation (FR-030-FR-038, FR-052, AC-002, RULE-007, RULE-011, RULE-013, RULE-015)."""

import hashlib
import io
import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.config import get_settings
from asset_studio.modules.audit.models import AuditEntry
from asset_studio.modules.generation import service as generation
from asset_studio.modules.models import catalogue as cat
from asset_studio.modules.poses.builtin import BUILTIN_POSES
from asset_studio.modules.poses.render import fit, openpose_png
from asset_studio.modules.providers.base import GenerationRequest
from asset_studio.modules.providers.comfyui import ComfyUIProvider
from asset_studio.modules.providers.engine import EngineMonitor
from asset_studio.modules.providers.fake import FakeProvider
from asset_studio.modules.providers.png import sample_image
from asset_studio.modules.references.models import ReferenceLink
from asset_studio.modules.workflows.builtin import ALL, Features, template
from tests.conftest import MCP, ORIGIN, project_config
from tests.test_jobs import _runner

FILES = {
    "xl": ("checkpoint", "sdxl", "checkpoints"),
    "v15": ("checkpoint", "sd15", "checkpoints"),
    "xlvae": ("vae", "sdxl", "vae"),
    "pose-xl": ("controlnet", "sdxl", "controlnet"),
    "ipa-xl": ("ip_adapter", "sdxl", "ipadapter"),
    "clip": ("clip_vision", None, "clip_vision"),
    "nc-xl": ("checkpoint", "sdxl", "checkpoints"),
}


def _blob(model_id: str) -> bytes:
    return f"weights {model_id}".encode()


CATALOGUE = {
    "schema_version": 1,
    "version": 1,
    "families": [{"id": "sdxl", "name": "SDXL"}, {"id": "sd15", "name": "SD 1.5"}],
    "licences": [
        {"id": "mit", "name": "MIT", "commercial_use": "allowed"},
        {"id": "nc", "name": "Non-commercial", "commercial_use": "forbidden"},
        {"id": "unknown", "name": "Not stated", "commercial_use": "unknown"},
    ],
    "models": [
        {
            "id": mid,
            "name": mid,
            "kind": kind,
            "family": family,
            "file_name": f"{mid}.safetensors",
            "source_url": f"https://models.example/{mid}",
            "sha256": hashlib.sha256(_blob(mid)).hexdigest(),
            "bytes": len(_blob(mid)),
            "licence": "nc" if mid == "nc-xl" else "mit",
        }
        for mid, (kind, family, _) in FILES.items()
    ],
}


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    fake = FakeProvider(steps=2)
    monitor = EngineMonitor(fake, ttl=0)
    monkeypatch.setattr(generation, "get_engine_monitor", lambda: monitor)
    return fake


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, storage: Any) -> Iterator[Path]:
    root = tmp_path / "models"
    monkeypatch.setenv("ASSET_STUDIO_MODELS_DIR", str(root))
    get_settings.cache_clear()
    monkeypatch.setattr(cat, "load", lambda: cat.Catalogue.model_validate(CATALOGUE))
    monkeypatch.setattr(generation, "get_storage", lambda: storage)
    for mid, (_, _, folder) in FILES.items():
        if mid == "v15":
            continue
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / f"{mid}.safetensors").write_bytes(_blob(mid))
    yield root
    get_settings.cache_clear()


@pytest.fixture
def api(client: TestClient, engine: FakeProvider, installed: Path) -> TestClient:
    from asset_studio.modules.providers.engine import get_engine_monitor

    client.app.dependency_overrides[get_engine_monitor] = generation.get_engine_monitor  # type: ignore[attr-defined]
    return client


def _project(client: TestClient, intended_use: str = "non_commercial") -> str:
    r = client.post(
        "/api/v1/projects", json=project_config(intended_use=intended_use), headers=ORIGIN
    )
    return str(r.json()["id"])


def _style_character(client: TestClient, pid: str) -> tuple[str, str]:
    style = client.post(
        f"/api/v1/projects/{pid}/styles",
        json={
            "name": "Flat",
            "attributes": {
                "description": "flat vector illustration",
                "lighting": "soft light",
                "avoid": ["text", "watermark"],
            },
        },
        headers=ORIGIN,
    ).json()
    character = client.post(
        f"/api/v1/projects/{pid}/characters",
        json={
            "name": "Ola",
            "description": "woman in her thirties",
            "attributes": {"traits": {"hair": "short dark bob"}, "avoid": ["glasses"]},
        },
        headers=ORIGIN,
    ).json()
    return style["id"], character["id"]


def _reference(client: TestClient, pid: str) -> str:
    r = client.post(
        f"/api/v1/projects/{pid}/references",
        params={"role": "character", "name": "ola.png"},
        content=sample_image(96, 128, seed=7),
        headers={**ORIGIN, "Content-Type": "image/png"},
    )
    return str(r.json()["id"])


def _spec(pid: str, **extra: Any) -> dict[str, Any]:
    return {
        "project_id": pid,
        "asset": {"category": "core", "name": "Squat"},
        "checkpoint_id": "xl",
        "prompt": "doing a squat",
        "width": 512,
        "height": 512,
        "steps": 4,
        **extra,
    }


# --- workflows and pose images -----------------------------------------------------------------


def test_every_builtin_workflow_renders() -> None:
    assert len(ALL) == 16 and len({f.id for f in ALL}) == 16
    for f in ALL:
        t = template(f)
        values = {name: spec.default for name, spec in t.inputs.items() if spec.default is not None}
        for name, spec in t.inputs.items():
            if name not in values:
                values[name] = (
                    "x"
                    if spec.type == "string"
                    else type(1 if spec.type == "integer" else 0.5)(spec.minimum or 1)
                )
        graph = t.render(values)
        # Every node link points at a node in the graph.
        for node in graph.values():
            for value in node["inputs"].values():
                if isinstance(value, list):
                    assert value[0] in graph, (f.id, value)
    assert Features(pose=True, reference=True).required_kinds() == (
        "checkpoint",
        "controlnet",
        "ip_adapter",
        "clip_vision",
    )


def test_pose_image_is_fitted_and_centred() -> None:
    assert fit(0.75, 1024, 1024) == (128.0, 0.0, 768.0, 1024.0)
    assert fit(0.75, 600, 1600) == (0.0, 400.0, 600.0, 800.0)
    png = openpose_png(BUILTIN_POSES[0].keypoints, 0.75, 512, 512)
    img = Image.open(io.BytesIO(png))
    assert img.size == (512, 512) and img.getpixel((5, 5)) == (0, 0, 0)
    assert img.getbbox() is not None  # something was drawn


# --- planning and checks ----------------------------------------------------------------------


def test_check_composes_prompts_and_picks_models(api: TestClient) -> None:
    pid = _project(api)
    style, character = _style_character(api, pid)
    r = api.post(
        "/api/v1/generations:check",
        json=_spec(pid, style_id=style, character_id=character, negative="blurry"),
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["ready"] is True and c["problems"] == []
    assert c["workflow"] == {"id": "txt2img+vae", "version": 1}
    assert c["models"] == {"checkpoint": "xl", "vae": "xlvae"}
    assert c["prompts"] == [
        "doing a squat, woman in her thirties, hair: short dark bob, flat vector illustration, "
        "soft light"
    ]
    assert c["negative"] == "blurry, text, watermark, glasses"
    assert c["engine"] == {"available": True, "reason": None}


def test_rule015_and_missing_models_are_reported(api: TestClient, installed: Path) -> None:
    pid = _project(api)
    pose = str(BUILTIN_POSES[0].id)
    # The SD 1.5 checkpoint is not installed and nothing for SD 1.5 exists to pose it.
    c = api.post(
        "/api/v1/generations:check",
        json=_spec(pid, checkpoint_id="v15", pose_id=pose, vae_id="xlvae"),
        headers=ORIGIN,
    ).json()
    codes = sorted(p["code"] for p in c["problems"])
    assert codes == ["FAMILY_MISMATCH", "MODEL_NOT_INSTALLED", "MODEL_REQUIRED"]
    assert c["ready"] is False
    empty = api.post("/api/v1/generations:check", json=_spec(pid, prompt=""), headers=ORIGIN).json()
    assert [p["code"] for p in empty["problems"]] == ["PROMPT_REQUIRED"]
    r = api.post("/api/v1/generations", json=_spec(pid, prompt=""), headers=ORIGIN)
    assert (r.status_code, r.json()["code"]) == (422, "GENERATION_NOT_READY")


def test_rule007_licence_must_be_confirmed_before_queueing(api: TestClient) -> None:
    pid = _project(api, "commercial")
    spec = _spec(pid, checkpoint_id="nc-xl")
    c = api.post("/api/v1/generations:check", json=spec, headers=ORIGIN).json()
    assert c["licence_confirmation_required"] == ["nc-xl"] and c["ready"] is False
    r = api.post("/api/v1/generations", json=spec, headers=ORIGIN)
    assert (r.status_code, r.json()["code"]) == (409, "LICENCE_CONFIRMATION_REQUIRED")
    api.post(
        f"/api/v1/projects/{pid}/licence-acknowledgements",
        json={"model_id": "nc-xl"},
        headers=ORIGIN,
    )
    assert api.post("/api/v1/generations", json=spec, headers=ORIGIN).status_code == 202


def test_inputs_from_another_project_are_rejected(api: TestClient) -> None:
    pid, other = _project(api), _project(api)
    style, _ = _style_character(api, other)
    r = api.post("/api/v1/generations:check", json=_spec(pid, style_id=style), headers=ORIGIN)
    assert (r.status_code, r.json()["code"]) == (422, "STYLE_OTHER_PROJECT")


# --- queueing ----------------------------------------------------------------------------------


def test_fr034_variants_and_batch(api: TestClient, db: Session) -> None:
    pid = _project(api)
    r = api.post("/api/v1/generations", json=_spec(pid, variants=3, seed=100), headers=ORIGIN)
    assert r.status_code == 202, r.text
    q = r.json()
    assert len(q["asset_ids"]) == 1 and len(q["jobs"]) == 3
    assert {(j["kind"], j["lane"]) for j in q["jobs"]} == {("generate", "gpu")}
    assert [j["params"]["plan"]["seed"] for j in q["jobs"]] == [100, 101, 102]
    batch = api.post(
        "/api/v1/generations",
        json=_spec(
            pid, batch=[{"name": "Lunge", "prompt": "lunge"}, {"name": "Plank", "prompt": "plank"}]
        ),
        headers=ORIGIN,
    ).json()
    assert len(batch["asset_ids"]) == 2 and len(batch["jobs"]) == 2
    assert batch["jobs"][1]["params"]["plan"]["positive"].startswith("doing a squat, plank")
    assert db.scalar(select(AuditEntry).where(AuditEntry.action == "generation.queued"))


def test_rule013_queueing_works_while_the_engine_is_down(
    api: TestClient, engine: FakeProvider
) -> None:
    engine.available = False
    pid = _project(api)
    c = api.post("/api/v1/generations:check", json=_spec(pid), headers=ORIGIN).json()
    assert c["engine"] == {"available": False, "reason": "ENGINE_UNAVAILABLE"}
    assert api.post("/api/v1/generations", json=_spec(pid), headers=ORIGIN).status_code == 202


# --- the job, metadata and regeneration -----------------------------------------------------


def _run(connection: Connection) -> None:
    _runner(connection, {"generate": generation.handle_generate}).tick()


def test_fr033_pose_and_reference_job_stores_versions_with_metadata(
    api: TestClient, engine: FakeProvider, connection: Connection, db: Session
) -> None:
    pid = _project(api)
    style, character = _style_character(api, pid)
    ref = _reference(api, pid)
    pose = BUILTIN_POSES[0]
    q = api.post(
        "/api/v1/generations",
        json=_spec(
            pid,
            style_id=style,
            character_id=character,
            pose_id=str(pose.id),
            pose_strength=0.9,
            reference={"reference_id": ref, "weight": 0.5},
            seed=42,
        ),
        headers=ORIGIN,
    ).json()
    _run(connection)
    job = api.get(f"/api/v1/jobs/{q['jobs'][0]['id']}").json()
    assert job["state"] == "completed", job
    (version_id,) = job["result"]["versions"]
    sent = engine.images[0]
    assert Image.open(io.BytesIO(sent["pose_image"])).size == (512, 512)
    assert sent["reference_image"] == sample_image(96, 128, seed=7)
    version = api.get(f"/api/v1/versions/{version_id}").json()
    assert (version["state"], version["width"], version["height"]) == ("processing", 512, 512)
    # Post-processing follows on its own (FR-065, T-02).
    queued = api.get("/api/v1/jobs", params={"kind": "process"}).json()
    assert [j["params"]["version_id"] for j in queued] == [version_id]
    meta = db.scalar(select(AuditEntry.data).where(AuditEntry.action == "asset_version.generated"))
    assert meta is not None
    from asset_studio.modules.assets.models import AssetVersion

    stored = db.get(AssetVersion, uuid.UUID(version_id))
    assert stored is not None
    m = stored.generation_metadata
    assert m["workflow"] == {"id": "txt2img+pose+reference+vae", "version": 1}
    assert (m["seed"], m["steps"], m["engine"]["name"]) == (42, 4, "fake")
    assert m["models"]["checkpoint"]["sha256"] == hashlib.sha256(_blob("xl")).hexdigest()
    assert m["pose"]["id"] == str(pose.id) and m["pose"]["strength"] == 0.9
    assert m["references"] == [
        {"id": ref, "sha256": m["references"][0]["sha256"], "weight": 0.5, "end": 1.0}
    ]
    assert m["style"]["version"] == 1 and m["hardware"]["gpu"] == "Fake GPU"
    links = {(lk.target_type, str(lk.target_id)) for lk in db.scalars(select(ReferenceLink))}
    assert ("job", q["jobs"][0]["id"]) in links and ("asset_version", version_id) in links


def test_ac002_regenerate_makes_a_new_version(
    api: TestClient, connection: Connection, db: Session
) -> None:
    pid = _project(api)
    q = api.post("/api/v1/generations", json=_spec(pid, seed=7), headers=ORIGIN).json()
    _run(connection)
    first = api.get(f"/api/v1/jobs/{q['jobs'][0]['id']}").json()["result"]["versions"][0]
    r = api.post(
        f"/api/v1/versions/{first}:regenerate", json={"seed": 8, "steps": 6}, headers=ORIGIN
    )
    assert r.status_code == 202, r.text
    again = r.json()
    assert again["asset_ids"] == q["asset_ids"]
    plan = again["jobs"][0]["params"]["plan"]
    assert (plan["seed"], plan["params"]["steps"]) == (8, 6)
    _run(connection)
    versions = api.get(f"/api/v1/assets/{q['asset_ids'][0]}/versions").json()
    assert [v["number"] for v in versions] == [1, 2] or [v["number"] for v in versions] == [2, 1]
    assert api.get(f"/api/v1/versions/{first}").json()["state"] == "processing"
    bad = api.post(f"/api/v1/versions/{first}:regenerate", json={"project_id": pid}, headers=ORIGIN)
    assert bad.json()["code"] == "REGENERATE_FIELD_FIXED"


def test_engine_failure_fails_the_job(
    api: TestClient, engine: FakeProvider, connection: Connection
) -> None:
    engine.fail_with = "CUDA out of memory"
    pid = _project(api)
    q = api.post("/api/v1/generations", json=_spec(pid), headers=ORIGIN).json()
    _run(connection)
    job = api.get(f"/api/v1/jobs/{q['jobs'][0]['id']}").json()
    assert (job["state"], job["error"]["code"]) == ("failed", "GENERATION_FAILED")
    assert "out of memory" in job["error"]["message"]


def test_claude_can_queue_generation(api: TestClient) -> None:
    pid = _project(api)
    assert api.post("/api/v1/generations", json=_spec(pid), headers=MCP).status_code == 202


# --- ComfyUI adapter: image upload and step progress -------------------------------------------


def test_comfyui_uploads_images_and_reports_steps() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/image":
            seen["upload"] = request.content
            return httpx.Response(
                200, json={"name": "asset_studio_x.png", "subfolder": "", "type": "input"}
            )
        if request.url.path == "/prompt":
            seen["prompt"] = json.loads(request.content)["prompt"]
            return httpx.Response(200, json={"prompt_id": "p1"})
        if request.url.path == "/history/p1":
            return httpx.Response(200, json={})
        if request.url.path == "/queue":
            return httpx.Response(200, json={"queue_running": [[0, "p1"]], "queue_pending": []})
        return httpx.Response(404)

    provider = ComfyUIProvider(
        "http://comfy",
        client=httpx.Client(base_url="http://comfy", transport=httpx.MockTransport(handler)),
        listen_steps=False,
    )
    t = template(Features(pose=True))
    values = {
        "checkpoint": "a.safetensors",
        "prompt": "p",
        "seed": 1,
        "steps": 20,
        "cfg": 5.0,
        "sampler": "euler",
        "scheduler": "karras",
        "width": 512,
        "height": 512,
        "controlnet": "c.safetensors",
        "pose_strength": 1.0,
        "pose_end": 1.0,
    }
    ref = provider.submit(GenerationRequest(t, values, {"pose_image": b"\x89PNG fake"}))
    assert ref == "p1" and b"\x89PNG fake" in seen["upload"]
    assert seen["prompt"]["11"]["inputs"]["image"] == "asset_studio_x.png"
    assert provider.progress("p1").step is None
    provider.on_message(
        json.dumps({"type": "progress", "data": {"value": 7, "max": 20, "prompt_id": "p1"}})
    )
    provider.on_message("not json")
    p = provider.progress("p1")
    assert (p.state, p.step, p.of) == ("running", 7, 20)
