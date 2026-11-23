"""Post-processing and technical validation (FR-060, FR-065, T-02 to T-04, RULE-003,
RULE-007, RULE-009, RULE-013, ADR-010)."""

import hashlib
import io
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.config import get_settings
from asset_studio.errors import DomainError
from asset_studio.modules.assets import service as assets
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.models import catalogue as cat
from asset_studio.modules.processing import imaging
from asset_studio.modules.processing import service as processing
from asset_studio.modules.providers.engine import EngineMonitor
from asset_studio.modules.providers.fake import FakeProvider
from asset_studio.modules.quality.validation import Expectations, render_name, validate
from asset_studio.modules.workflows.builtin import remove_background
from tests.conftest import ORIGIN, project_config
from tests.test_jobs import _runner

WEIGHTS = b"birefnet weights"
CATALOGUE = {
    "schema_version": 1,
    "version": 1,
    "families": [{"id": "sdxl", "name": "SDXL"}],
    "licences": [
        {"id": "mit", "name": "MIT", "commercial_use": "allowed"},
        {"id": "unknown", "name": "Not stated", "commercial_use": "unknown"},
    ],
    "models": [
        {
            "id": "birefnet-comfy",
            "name": "BiRefNet",
            "kind": "segmentation",
            "family": None,
            "file_name": "birefnet.safetensors",
            "source_url": "https://models.example/birefnet",
            "sha256": hashlib.sha256(WEIGHTS).hexdigest(),
            "bytes": len(WEIGHTS),
            "licence": "mit",
        }
    ],
}


def _png(size: tuple[int, int], colour: tuple[int, ...], mode: str = "RGB") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, colour).save(out, "PNG")
    return out.getvalue()


def _subject(size: tuple[int, int], background: tuple[int, int, int]) -> bytes:
    """A dark square in the middle of a flat background."""
    image = Image.new("RGB", size, background)
    w, h = size
    image.paste((20, 40, 160), (w // 4, h // 4, 3 * w // 4, 3 * h // 4))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _open(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


# --- imaging (pure) -------------------------------------------------------------------------


def test_fr065_contain_pads_cover_crops_none_keeps() -> None:
    src = _png((80, 40), (200, 10, 10))
    contained = imaging.process(src, imaging.Target(64, 64, "png", "any"))
    assert (contained.width, contained.height) == (64, 64)
    assert _open(contained.data).getpixel((0, 0)) == (255, 255, 255)  # padded
    assert contained.steps[0] == {
        "step": "resize",
        "mode": "contain",
        "from": [80, 40],
        "to": [64, 64],
    }
    covered = imaging.process(src, imaging.Target(64, 64, "png", "any", resize="cover"))
    assert _open(covered.data).getpixel((0, 0)) == (200, 10, 10)  # cropped, no padding
    kept = imaging.process(src, imaging.Target(64, 64, "png", "any", resize="none"))
    assert (kept.width, kept.height) == (80, 40)


def test_fr065_transparent_padding_white_fill_jpeg_and_webp() -> None:
    rgba = _png((40, 20), (0, 200, 0, 255), "RGBA")
    padded = _open(imaging.process(rgba, imaging.Target(40, 40, "png", "transparent")).data)
    assert padded.mode == "RGBA" and padded.getpixel((0, 0))[3] == 0
    white = imaging.process(rgba, imaging.Target(40, 40, "png", "white"))
    assert _open(white.data).mode == "RGB"
    assert {"step": "background", "fill": "white"} in white.steps
    jpeg = imaging.process(rgba, imaging.Target(40, 40, "jpeg", "transparent", quality=80))
    assert (jpeg.mime, jpeg.ext, _open(jpeg.data).format) == ("image/jpeg", "jpg", "JPEG")
    assert {"step": "convert", "from": "png", "to": "jpeg"} in jpeg.steps
    webp = imaging.process(rgba, imaging.Target(40, 20, "webp", "any"))
    assert _open(webp.data).format == "WEBP" and webp.steps[0]["step"] == "convert"


def test_fr065_cutout_uses_mask_as_alpha_and_derived_sizes() -> None:
    original = _png((32, 32), (10, 20, 30))
    mask = Image.new("L", (16, 16), 0)
    mask.paste(255, (4, 4, 12, 12))
    buf = io.BytesIO()
    mask.save(buf, "PNG")
    cut = _open(imaging.cutout(original, buf.getvalue()))
    assert cut.mode == "RGBA" and cut.size == (32, 32)
    assert cut.getpixel((0, 0))[3] == 0 and cut.getpixel((16, 16)) == (10, 20, 30, 255)
    big = imaging.process(original, imaging.Target(1200, 600, "png", "any"))
    thumb = _open(imaging.derived(big.data, 256))
    assert thumb.format == "WEBP" and thumb.size == (256, 128)


def test_fr065_broken_image_is_reported() -> None:
    with pytest.raises(imaging.ProcessingError) as exc:
        imaging.process(b"\x89PNG\r\n\x1a\nbroken", imaging.Target(8, 8, "png", "any"))
    assert exc.value.code == "IMAGE_UNREADABLE"


# --- validation (pure) ----------------------------------------------------------------------


def _expect(data: bytes, **kw: Any) -> Expectations:
    values: dict[str, Any] = {
        "width": 64,
        "height": 64,
        "format": "png",
        "background": "any",
        "max_file_kb": None,
        "aspect_tolerance": 0.01,
        "sha256": hashlib.sha256(data).hexdigest(),
        "file_name": "squat-main.png",
    }
    return Expectations(**(values | kw))


def _by_rule(data: bytes, **kw: Any) -> dict[str, tuple[str, dict[str, Any]]]:
    return {r.rule: (r.status, r.details) for r in validate(data, _expect(data, **kw))}


def test_fr060_rules_pass_for_a_matching_file() -> None:
    data = _png((64, 64), (255, 255, 255))
    rules = _by_rule(data, background="white", max_file_kb=50)
    assert list(rules) == [
        "integrity",
        "format",
        "dimensions",
        "aspect_ratio",
        "file_size",
        "transparency",
        "naming",
    ]
    assert {status for status, _ in rules.values()} == {"passed"}


def test_fr060_rules_fail_with_details() -> None:
    data = _subject((80, 64), (128, 128, 128))  # grey background, wrong size
    rules = _by_rule(
        data,
        format="webp",
        background="white",
        sha256="0" * 64,
        file_name="Squat Main.png",
        collisions=("squat",),
    )
    assert rules["integrity"] == ("failed", {"decoded": True, "sha256_matches": False})
    assert rules["format"] == ("failed", {"expected": "webp", "actual": "png"})
    assert rules["dimensions"][0] == "failed" and rules["aspect_ratio"][0] == "failed"
    assert rules["file_size"][0] == "skipped"
    status, details = rules["transparency"]
    assert status == "failed" and details["white_edge"] == 0
    assert rules["naming"] == (
        "failed",
        {"name": "Squat Main.png", "problems": ["characters", "collision"], "same_as": ["squat"]},
    )


def test_fr060_transparency_and_size_limits() -> None:
    cut = _png((64, 64), (0, 0, 0, 0), "RGBA")
    assert _by_rule(cut, background="transparent")["transparency"][0] == "passed"
    opaque = _png((64, 64), (255, 255, 255))
    status, details = _by_rule(opaque, background="transparent")["transparency"]
    assert status == "failed" and details["alpha_channel"] is False
    assert _by_rule(opaque, max_file_kb=1)["file_size"][0] == "passed"
    noise = Image.effect_noise((256, 256), 100).convert("RGB")
    buf = io.BytesIO()
    noise.save(buf, "PNG")
    assert _by_rule(buf.getvalue(), max_file_kb=1)["file_size"][0] == "failed"
    broken = _by_rule(b"not an image")
    assert broken["integrity"] == ("failed", {"decoded": False})
    assert broken["naming"] == ("skipped", {"reason": "unreadable"})


def test_fr060_naming_pattern_values() -> None:
    values = {"asset": "squat", "view": "front", "category": "lower-body", "version": "v2"}
    assert render_name("{category}-{asset}-{view}-{version}", values) == (
        "lower-body-squat-front-v2"
    )


def test_adr010_background_template_uses_native_nodes() -> None:
    graph = remove_background().render({"image": "in.png", "model": "birefnet.safetensors"})
    types = {node["class_type"] for node in graph.values()}
    assert types == {
        "LoadImage",
        "LoadBackgroundRemovalModel",
        "RemoveBackground",
        "MaskToImage",
        "SaveImage",
    }


# --- the pipeline ---------------------------------------------------------------------------


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch, storage: Any) -> FakeProvider:
    fake = FakeProvider(steps=1)
    monitor = EngineMonitor(fake, ttl=0)
    monkeypatch.setattr(processing, "get_engine_monitor", lambda: monitor)
    monkeypatch.setattr(processing, "get_storage", lambda: storage)
    return fake


@pytest.fixture
def models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "models"
    (root / "background_removal").mkdir(parents=True)
    monkeypatch.setenv("ASSET_STUDIO_MODELS_DIR", str(root))
    get_settings.cache_clear()
    monkeypatch.setattr(cat, "load", lambda: cat.Catalogue.model_validate(CATALOGUE))
    yield root
    get_settings.cache_clear()


def _install(root: Path) -> None:
    (root / "background_removal" / "birefnet.safetensors").write_bytes(WEIGHTS)


def _project(client: TestClient, **output: Any) -> tuple[str, dict[str, Any]]:
    cfg = project_config(
        output={"width": 64, "height": 64, "format": "png", "background": "any"} | output
    )
    r = client.post("/api/v1/projects", json=cfg, headers=ORIGIN)
    assert r.status_code == 201, r.text
    return str(r.json()["id"]), cfg


def _configure(client: TestClient, pid: str, cfg: dict[str, Any], **changes: Any) -> None:
    r = client.put(
        f"/api/v1/projects/{pid}/config",
        json={"config": cfg | changes, "acknowledge_breaking": True},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text


def _version(db: Session, storage: Any, pid: str, data: bytes, name: str = "Squat") -> uuid.UUID:
    asset = assets.create_asset(db, uuid.UUID(pid), category="lower-body", name=name, actor="user")
    version = assets.add_version(
        db, storage, asset.id, io.BytesIO(data), mime="image/png", actor="system"
    )
    db.flush()
    return version.id


def _run(connection: Connection, **kw: Any) -> None:
    runner = _runner(connection, processing.HANDLERS, **kw)
    for _ in range(4):  # remove_background, then process
        if not runner.tick():
            break


def test_fr065_process_validate_and_review(
    client: TestClient, db: Session, storage: Any, connection: Connection, engine: FakeProvider
) -> None:
    pid, _ = _project(client, background="white", format="webp")
    original = _subject((80, 80), (255, 255, 255))
    vid = _version(db, storage, pid, original)
    r = client.post(f"/api/v1/versions/{vid}:process", headers=ORIGIN)
    assert r.status_code == 202, r.text
    assert r.json()["kind"] == "process" and r.json()["enqueued_by_actor"] == "user"
    assert client.get(f"/api/v1/versions/{vid}").json()["state"] == "processing"
    again = client.post(f"/api/v1/versions/{vid}:process", headers=ORIGIN)
    assert again.json()["code"] == "PROCESSING_NOT_ALLOWED"

    _run(connection)
    version = client.get(f"/api/v1/versions/{vid}").json()
    assert version["state"] == "awaiting_review"  # T-03
    p = version["processing"]
    out = p["output"]
    assert (out["mime"], out["width"], out["height"]) == ("image/webp", 64, 64)
    assert [s["step"] for s in p["steps"]] == ["resize", "convert", "optimize"]
    assert "key" not in out and p["background_removed"] is False
    assert [h["transition_id"] for h in version["history"]] == ["T-01", "T-02", "T-03"]
    stored = connection.execute(
        text("SELECT processing->>'dhash' FROM asset_version WHERE id = :id"), {"id": vid}
    ).scalar_one()
    assert len(stored) == 16  # the fingerprint for duplicate detection (FR-059)

    # The original is untouched (RULE-003); the processed and derived files are served.
    assert client.get(f"/api/v1/versions/{vid}/file").content == original
    processed = client.get(f"/api/v1/versions/{vid}/file?size=processed")
    assert processed.headers["content-type"] == "image/webp"
    assert hashlib.sha256(processed.content).hexdigest() == out["sha256"]
    assert _open(client.get(f"/api/v1/versions/{vid}/file?size=thumb").content).size == (64, 64)

    report = client.get(f"/api/v1/versions/{vid}/validation").json()
    assert [(r["rule"], r["status"]) for r in report["results"]] == list(
        {
            "integrity": "passed",
            "format": "passed",
            "dimensions": "passed",
            "aspect_ratio": "passed",
            "file_size": "skipped",
            "transparency": "passed",
            "naming": "passed",
        }.items()
    )
    assert report["summary"] == {"passed": 6, "failed": 0, "skipped": 1}
    naming = next(r for r in report["results"] if r["rule"] == "naming")
    assert naming["details"]["name"] == "squat-main.webp"


def test_rule009_failed_checks_do_not_block_review_and_revalidate(
    client: TestClient, db: Session, storage: Any, connection: Connection, engine: FakeProvider
) -> None:
    pid, cfg = _project(client, background="white")
    vid = _version(db, storage, pid, _subject((64, 64), (128, 128, 128)))  # grey (R-12)
    processing.start(db, vid, "user")
    db.flush()
    _run(connection)
    assert client.get(f"/api/v1/versions/{vid}").json()["state"] == "awaiting_review"
    first = client.get(f"/api/v1/versions/{vid}/validation").json()
    assert {r["rule"]: r["status"] for r in first["results"]}["transparency"] == "failed"

    _configure(client, pid, cfg, validation={"max_file_kb": 1}, naming="{category}")
    _version(db, storage, pid, _subject((64, 64), (255, 255, 255)), name="Lunge")
    r = client.post(f"/api/v1/versions/{vid}:validate", headers=ORIGIN)
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["run_id"] != first["run_id"]
    rules = {x["rule"]: x for x in second["results"]}
    assert rules["file_size"]["details"]["max_kb"] == 1
    assert rules["naming"]["status"] == "failed"
    assert rules["naming"]["details"]["same_as"] == ["lunge"]
    assert client.get(f"/api/v1/versions/{vid}/validation").json()["run_id"] == second["run_id"]


def test_adr010_background_removal_on_the_gpu_lane(
    client: TestClient,
    db: Session,
    storage: Any,
    connection: Connection,
    engine: FakeProvider,
    models: Path,
) -> None:
    pid, cfg = _project(client, background="transparent")
    _configure(client, pid, cfg, processing={"remove_background": True})
    _install(models)
    original = _subject((64, 64), (230, 230, 230))
    vid = _version(db, storage, pid, original)
    job = processing.start(db, vid, "system")
    db.flush()
    assert (job.kind, job.lane) == ("remove_background", "gpu")

    # Engine down: the step waits with the reason; nothing fails (RULE-013).
    _run(connection, gates={"gpu": lambda: "ENGINE_UNAVAILABLE"})
    waiting = client.get(f"/api/v1/jobs/{job.id}").json()
    assert (waiting["state"], waiting["wait_reason"]) == ("queued", "ENGINE_UNAVAILABLE")
    assert client.get(f"/api/v1/versions/{vid}").json()["state"] == "processing"

    _run(connection)
    assert engine.images[-1]["image"] == original
    version = client.get(f"/api/v1/versions/{vid}").json()
    assert version["state"] == "awaiting_review"
    assert version["processing"]["background_removed"] is True, version["processing"]
    assert version["processing"]["steps"][0] == {
        "step": "remove_background",
        "model": "birefnet-comfy",
    }
    processed = _open(client.get(f"/api/v1/versions/{vid}/file?size=processed").content)
    assert processed.mode == "RGBA" and processed.getpixel((0, 0))[3] == 0
    report = client.get(f"/api/v1/versions/{vid}/validation").json()
    assert {r["rule"]: r["status"] for r in report["results"]}["transparency"] == "passed"


def test_t04_missing_model_fails_and_retry_restarts(
    client: TestClient,
    db: Session,
    storage: Any,
    connection: Connection,
    engine: FakeProvider,
    models: Path,
) -> None:
    pid, cfg = _project(client, background="transparent")
    _configure(client, pid, cfg, processing={"remove_background": True})
    vid = _version(db, storage, pid, _subject((64, 64), (230, 230, 230)))
    job = processing.start(db, vid, "system")
    db.flush()
    _run(connection)
    failed = client.get(f"/api/v1/jobs/{job.id}").json()
    assert (failed["state"], failed["error"]["code"]) == ("failed", "PROCESSING_MODEL_MISSING")
    version = client.get(f"/api/v1/versions/{vid}").json()
    assert version["state"] == "processing_failed"  # T-04
    assert version["processing"]["error"]["code"] == "PROCESSING_MODEL_MISSING"
    assert version["processing"]["error"]["step"] == "remove_background"

    _install(models)
    r = client.post(
        f"/api/v1/versions/{vid}/transitions", json={"action": "retry_processing"}, headers=ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "processing" and r.json()["processing"]["error"] is None
    _run(connection)
    version = client.get(f"/api/v1/versions/{vid}").json()
    assert version["state"] == "awaiting_review"
    ids = [h["transition_id"] for h in version["history"]]
    assert ids == ["T-01", "T-02", "T-04", "T-04R", "T-03"]


def test_t04_queue_retry_of_a_failed_step_resumes_the_version(
    client: TestClient, db: Session, storage: Any, connection: Connection, engine: FakeProvider
) -> None:
    pid, _ = _project(client)
    vid = _version(db, storage, pid, b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)  # undecodable
    job = processing.start(db, vid, "user")
    db.flush()
    _run(connection)
    assert client.get(f"/api/v1/jobs/{job.id}").json()["error"]["code"] == "IMAGE_UNREADABLE"
    assert client.get(f"/api/v1/versions/{vid}").json()["state"] == "processing_failed"
    # Retrying the job from the queue returns the version to processing first (T-04R).
    jobs.retry(db, job.id, "user")
    db.flush()
    _run(connection)
    version = client.get(f"/api/v1/versions/{vid}").json()
    assert version["state"] == "processing_failed"
    assert [h["transition_id"] for h in version["history"]][-2:] == ["T-04R", "T-04"]


def test_processing_actor_rules(client: TestClient, db: Session, storage: Any) -> None:
    pid, _ = _project(client)
    vid = _version(db, storage, pid, _subject((64, 64), (255, 255, 255)))
    with pytest.raises(DomainError) as exc:
        processing.start(db, vid, "mcp")
    assert exc.value.code == "ACTOR_NOT_ALLOWED"
    assert client.get(f"/api/v1/versions/{vid}/file?size=processed").status_code == 404
    assert client.get(f"/api/v1/versions/{vid}/validation").json()["run_id"] is None
    not_yet = client.post(f"/api/v1/versions/{vid}:validate", headers=ORIGIN)
    assert not_yet.json()["code"] == "VERSION_NOT_PROCESSED"
