"""LoRA training (WP-13): datasets from approved versions and uploads (FR-070, RULE-017),
captions (FR-071), presets and estimates with the SDXL warning (FR-072, FR-073, RULE-016),
the train job with progress and cancellation (FR-074) and the registered LoRA (FR-075)."""

import io
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.config import get_settings
from asset_studio.modules.assets import service as assets
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.models import catalogue as cat
from asset_studio.modules.models.models import Model
from asset_studio.modules.projects.config_schema import ProjectConfig
from asset_studio.modules.projects.service import create_project
from asset_studio.modules.providers.engine import EngineMonitor, get_engine_monitor
from asset_studio.modules.providers.fake import FakeProvider
from asset_studio.modules.storage.local import LocalStorage
from asset_studio.modules.training import runner as train
from asset_studio.modules.training.models import TrainingRun
from tests.conftest import MCP, ORIGIN, project_config
from tests.test_generation import CATALOGUE, FILES, _blob
from tests.test_jobs import _runner

U = {**ORIGIN, "Idempotency-Key": "train-0001"}


def _png(colour: tuple[int, int, int], side: int = 320) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (side, side), colour).save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "models"
    monkeypatch.setenv("ASSET_STUDIO_MODELS_DIR", str(root))
    get_settings.cache_clear()
    monkeypatch.setattr(cat, "load", lambda: cat.Catalogue.model_validate(CATALOGUE))
    for mid, (_, _, folder) in FILES.items():
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / f"{mid}.safetensors").write_bytes(_blob(mid))
    yield root
    get_settings.cache_clear()


@pytest.fixture
def api(client: TestClient, models: Path) -> TestClient:
    """The GPU has 6 GB, like the reference machine."""
    monitor = EngineMonitor(FakeProvider(steps=1), ttl=0)
    monitor.status = lambda: {"devices": [{"vram_total_mb": 6144}], "agent": {}}  # type: ignore[method-assign]
    client.app.dependency_overrides[get_engine_monitor] = lambda: monitor  # type: ignore[attr-defined]
    return client


def _approved(db: Session, storage: LocalStorage, pid: uuid.UUID, n: int) -> list[str]:
    ids = []
    for i in range(n):
        asset = assets.create_asset(db, pid, category="core", name=f"Plank {i}", actor="system")
        image = io.BytesIO(_png((20 * i, 90, 160)))
        v = assets.add_version(db, storage, asset.id, image, mime="image/png", actor="system")
        assets.transition(db, v.id, "start_processing", "system")
        assets.transition(db, v.id, "processing_succeeded", "system")
        assets.transition(db, v.id, "approve", "user")
        ids.append(str(v.id))
    db.commit()
    return ids


def _dataset(api: TestClient, pid: uuid.UUID) -> str:
    r = api.post(
        f"/api/v1/projects/{pid}/datasets",
        json={"name": "Exerzio woman", "trigger_word": "exz_woman"},
        headers=ORIGIN,
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _project(db: Session) -> uuid.UUID:
    pid = create_project(db, ProjectConfig.model_validate(project_config()), "user").id
    db.commit()
    return pid


def test_fr070_rule017_datasets_take_approved_versions_and_uploads(
    api: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    datasets = f"/api/v1/projects/{pid}/datasets"
    bad = api.post(datasets, json={"name": "x", "trigger_word": "Exz Woman"}, headers=ORIGIN)
    assert bad.json()["code"] == "TRIGGER_WORD_INVALID"
    mcp = api.post(datasets, json={"name": "x", "trigger_word": "exz"}, headers=MCP)
    assert mcp.json()["code"] == "ACTOR_NOT_ALLOWED"
    ds = _dataset(api, pid)
    versions = _approved(db, storage, pid, 2)
    asset = assets.create_asset(db, pid, category="core", name="Draft", actor="system")
    image = io.BytesIO(_png((1, 2, 3)))
    draft = assets.add_version(db, storage, asset.id, image, mime="image/png", actor="system")
    db.commit()
    url = f"/api/v1/datasets/{ds}/items:versions"
    r = api.post(url, json={"version_ids": [str(draft.id)]}, headers=ORIGIN)
    assert r.json()["code"] == "VERSION_NOT_APPROVED"  # RULE-017
    r = api.post(url, json={"version_ids": versions}, headers=ORIGIN)
    assert [i["caption"] for i in r.json()] == ["Plank 0", "Plank 1"]
    again = api.post(url, json={"version_ids": versions}, headers=ORIGIN)
    assert again.json() == []  # already in the dataset

    upload = f"/api/v1/datasets/{ds}/items?caption=side%20view"
    png = _png((200, 10, 10))
    r = api.post(upload, content=png, headers=ORIGIN | {"Content-Type": "image/png"})
    assert r.status_code == 201 and r.json()["source"] == "upload"
    item = r.json()["id"]
    dup = api.post(upload, content=png, headers=ORIGIN | {"Content-Type": "image/png"})
    assert dup.json()["code"] == "IMAGE_DUPLICATE"
    tiny = api.post(upload, content=_png((0, 0, 0), 64), headers=ORIGIN)
    assert tiny.json()["code"] == "IMAGE_SIZE_OUT_OF_RANGE"
    fake = api.post(upload, content=b"<svg/>", headers=ORIGIN)
    assert fake.json()["code"] == "MEDIA_TYPE_UNSUPPORTED"

    # FR-071: captions
    caption = {"caption": "woman, side view"}
    r = api.patch(f"/api/v1/training-items/{item}", json=caption, headers=ORIGIN)
    assert r.json()["caption"] == "woman, side view"
    assert api.get(f"/api/v1/training-items/{item}/file").content == png
    assert api.get(f"/api/v1/datasets/{ds}").json()["images"] == 3
    assert api.delete(f"/api/v1/training-items/{item}", headers=ORIGIN).status_code == 204
    assert api.get(f"/api/v1/datasets/{ds}").json()["images"] == 2


def _ready(api: TestClient, db: Session, storage: LocalStorage) -> tuple[uuid.UUID, str]:
    pid = _project(db)
    ds = _dataset(api, pid)
    versions = _approved(db, storage, pid, 5)
    url = f"/api/v1/datasets/{ds}/items:versions"
    api.post(url, json={"version_ids": versions}, headers=ORIGIN)
    return pid, ds


def _estimate(api: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    r = api.post("/api/v1/training-runs:estimate", json=body, headers=ORIGIN)
    return dict(r.json())


def test_fr073_rule016_estimates_and_the_sdxl_warning(
    api: TestClient, db: Session, storage: LocalStorage
) -> None:
    small = _dataset(api, _project(db))
    too_small = _estimate(api, {"dataset_id": small, "family": "sd15", "base_model_id": "v15"})
    assert too_small["code"] == "DATASET_TOO_SMALL"
    _, ds = _ready(api, db, storage)
    sd15 = _estimate(api, {"dataset_id": ds, "family": "sd15", "base_model_id": "v15"})
    assert (sd15["steps"], sd15["resolution"], sd15["warning"]) == (500, 512, False)
    assert sd15["seconds"] == 90 + 500 * 0.8  # measured on the reference 6 GB GPU
    wrong = _estimate(api, {"dataset_id": ds, "family": "sd15", "base_model_id": "xl"})
    assert wrong["code"] == "BASE_MODEL_INVALID"
    xl = {"dataset_id": ds, "family": "sdxl", "base_model_id": "xl", "steps": 600}
    est = _estimate(api, xl)
    assert est["warning"] is True and est["seconds"] == 180 + 600 * 30  # 5 hours on 6 GB
    r = api.post("/api/v1/training-runs", json=xl, headers=U)
    assert (r.status_code, r.json()["code"]) == (409, "ESTIMATE_NOT_ACKNOWLEDGED")
    assert r.json()["estimate"]["warning"] is True
    acknowledged = xl | {"acknowledged_estimate": True}
    r = api.post("/api/v1/training-runs", json=acknowledged, headers=U)
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["job"]["kind"] == "train" and run["job"]["lane"] == "gpu"
    assert run["acknowledged_estimate"] is True
    key2 = ORIGIN | {"Idempotency-Key": "train-0002"}
    second = api.post("/api/v1/training-runs", json=acknowledged, headers=key2)
    assert second.json()["code"] == "TRAINING_ALREADY_QUEUED"
    key3 = MCP | {"Idempotency-Key": "train-mcp1"}
    assert api.post("/api/v1/training-runs", json=xl, headers=key3).json()["code"] == (
        "ACTOR_NOT_ALLOWED"
    )


class Recording(train.FakeTrainer):
    """The fake trainer, also keeping what kohya would read."""

    def start(self, spec: dict[str, Any]) -> None:
        images = self.root / spec["run_id"] / "img"
        self.captions = sorted(p.read_text("utf-8") for p in images.rglob("*.txt"))
        self.folders = [p.name for p in images.iterdir()]
        self.spec = spec
        super().start(spec)


@pytest.fixture
def trainer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, storage: LocalStorage) -> Recording:
    rec = Recording(tmp_path / "exchange", step_seconds=0)
    monkeypatch.setattr(train, "exchange_root", lambda: tmp_path / "exchange")
    monkeypatch.setattr(train, "get_trainer", lambda: rec)
    monkeypatch.setattr(train, "get_storage", lambda: storage)
    monkeypatch.setattr(train, "POLL_SECONDS", 0)
    return rec


def test_fr072_fr075_a_run_trains_and_registers_the_lora(
    api: TestClient,
    db: Session,
    storage: LocalStorage,
    connection: Connection,
    trainer: Recording,
    models: Path,
) -> None:
    pid, ds = _ready(api, db, storage)
    body = {"dataset_id": ds, "family": "sd15", "base_model_id": "v15", "steps": 300}
    run_id = api.post("/api/v1/training-runs", json=body, headers=U).json()["id"]
    runner = _runner(connection, train.HANDLERS)
    runner.tick()
    runner.wait_idle()
    db.expire_all()
    run = db.get(TrainingRun, uuid.UUID(run_id))
    assert run is not None and run.job_id is not None
    job = jobs.get_job(db, run.job_id)
    assert job.state == "completed", job.error
    assert job.progress.get("step") == 300
    # kohya read a class folder named after the trigger, and every caption starts with it
    assert trainer.folders == ["1_exz_woman"]
    assert trainer.captions[0] == "exz_woman, Plank 0" and len(trainer.captions) == 5
    assert trainer.spec["base_model"] == "v15.safetensors" and trainer.spec["vae"] is None
    model = db.scalars(select(Model).where(Model.id == run.output_model_id)).one()
    assert (model.kind, model.family_id, model.licence_id, model.status) == (
        "lora",
        "sd15",
        "mit",
        "installed",
    )
    assert (models / "loras" / model.file_name).is_file()
    assert model.file_name.startswith("exz-woman-sd15-")
    listed = api.get(f"/api/v1/training-runs?project_id={pid}").json()
    assert listed[0]["output_model_id"] == model.id


def test_fr074_cancelling_stops_kohya(
    api: TestClient,
    db: Session,
    storage: LocalStorage,
    connection: Connection,
    trainer: Recording,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, ds = _ready(api, db, storage)
    body = {"dataset_id": ds, "family": "sd15", "base_model_id": "v15"}
    r = api.post("/api/v1/training-runs", json=body, headers=U).json()
    cancelled: list[str] = []

    def running(run_id: str) -> dict[str, Any]:
        jobs.cancel(db, uuid.UUID(r["job_id"]), "user")  # the user presses Cancel meanwhile
        db.commit()
        return {"state": "running", "step": 10, "total": 500}

    monkeypatch.setattr(trainer, "status", running)
    monkeypatch.setattr(trainer, "cancel", lambda run_id: cancelled.append(run_id))
    runner = _runner(connection, train.HANDLERS)
    runner.tick()
    runner.wait_idle()
    db.expire_all()
    assert jobs.get_job(db, uuid.UUID(r["job_id"])).state == "cancelled"
    assert cancelled == [r["id"]]


def test_training_starts_while_the_engine_is_down(db: Session, connection: Connection) -> None:
    """Training stops ComfyUI itself, so the engine gate does not hold it back."""
    ran: list[str] = []
    handlers = {k: (lambda ctx, k=k: ran.append(k)) for k in ("generate", "train")}
    gen = jobs.enqueue(db, "generate", {}, actor="user")
    jobs.enqueue(db, "train", {}, actor="user")
    db.commit()
    gates = {"gpu": lambda: "ENGINE_UNAVAILABLE"}
    runner = _runner(connection, handlers, gates=gates)  # type: ignore[arg-type]
    runner.tick()
    db.expire_all()
    assert ran == ["train"]
    assert jobs.get_job(db, gen.id).state == "queued"
