"""Model registry (FR-080-FR-084, RULE-007, RULE-008, RULE-015, NFR-007)."""

import hashlib
import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.config import get_settings
from asset_studio.errors import DomainError
from asset_studio.modules.audit.models import AuditEntry
from asset_studio.modules.models import catalogue as cat
from asset_studio.modules.models import service
from tests.conftest import MCP, ORIGIN, project_config
from tests.test_jobs import _runner

BLOB = {name: f"weights of {name}".encode() * 50 for name in ("base", "lora15", "ipa", "clip")}


def _entry(id: str, kind: str, family: str | None, file: str, licence: str = "mit") -> dict:
    return {
        "id": id,
        "name": id,
        "kind": kind,
        "family": family,
        "file_name": file,
        "source_url": f"https://models.example/{file}",
        "sha256": hashlib.sha256(BLOB[file.split(".")[0]]).hexdigest(),
        "bytes": len(BLOB[file.split(".")[0]]),
        "licence": licence,
        "notes": "",
    }


TEST_CATALOGUE = {
    "schema_version": 1,
    "version": 1,
    "families": [{"id": "sdxl", "name": "SDXL"}, {"id": "sd15", "name": "SD 1.5"}],
    "licences": [
        {"id": "mit", "name": "MIT", "commercial_use": "allowed"},
        {"id": "nc", "name": "Non-commercial", "commercial_use": "forbidden"},
        {"id": "unknown", "name": "Not stated", "commercial_use": "unknown"},
    ],
    "models": [
        _entry("base", "checkpoint", "sdxl", "base.safetensors"),
        _entry("lora15", "lora", "sd15", "lora15.safetensors", licence="nc"),
        _entry("ipa", "ip_adapter", "sdxl", "ipa.safetensors"),
        _entry("clip", "clip_vision", None, "clip.safetensors"),
    ],
}


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("ASSET_STUDIO_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("ASSET_STUDIO_POSE_MODELS_DIR", str(tmp_path / "pose"))
    get_settings.cache_clear()
    monkeypatch.setattr(cat, "load", lambda: cat.Catalogue.model_validate(TEST_CATALOGUE))
    yield tmp_path / "models"
    get_settings.cache_clear()
    service.set_http_client_factory(service.http_client)


def _put(root: Path, folder: str, name: str, data: bytes) -> Path:
    path = root / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _models(client: TestClient, **params: Any) -> dict[str, Any]:
    r = client.get("/api/v1/models", params=params)
    assert r.status_code == 200, r.text
    return {m["id"]: m for m in r.json()}


def _project(client: TestClient, intended_use: str = "commercial") -> str:
    r = client.post(
        "/api/v1/projects", json=project_config(intended_use=intended_use), headers=ORIGIN
    )
    return str(r.json()["id"])


# --- catalogue -------------------------------------------------------------------------------


def test_the_shipped_catalogue_is_valid() -> None:
    c = cat.parse(cat.PATH.read_text(encoding="utf-8"))
    assert {m.kind for m in c.models} >= {"checkpoint", "controlnet", "ip_adapter", "pose"}
    assert all(m.source_url.startswith("https://") for m in c.models)


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c["models"][0].update(source_url="http://insecure.example/x"),
        lambda c: c["models"][0].update(sha256="nothex"),
        lambda c: c["models"][1].update(id="base"),
        lambda c: c["models"][0].update(licence="missing"),
        lambda c: c["models"][0].update(file_name="../escape.safetensors"),
    ],
)
def test_bad_catalogues_are_rejected(change: Any) -> None:
    broken = json.loads(json.dumps(TEST_CATALOGUE))
    change(broken)
    with pytest.raises(ValidationError):
        cat.Catalogue.model_validate(broken)


# --- registry and scan (FR-080, FR-081) ------------------------------------------------------


def test_fr080_registry_lists_catalogue_models(client: TestClient, registry: Path) -> None:
    models = _models(client)
    assert set(models) == {"base", "lora15", "ipa", "clip"}
    base = models["base"]
    assert (base["status"], base["family_id"], base["origin"]) == ("available", "sdxl", "catalogue")
    assert base["licence"]["commercial_use"] == "allowed"
    assert base["vram_mb"] == 1  # weights size, rounded up to a MB


def test_fr081_scan_finds_installed_and_unknown_files(
    client: TestClient, registry: Path, db: Session
) -> None:
    _put(registry, "checkpoints", "base.safetensors", BLOB["base"])
    _put(registry, "loras", "my-style.safetensors", b"local lora")
    _put(registry, "loras", "notes.txt", b"ignored")
    r = client.post("/api/v1/models:rescan", headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["added"] == ["local-lora-my-style"]
    models = _models(client)
    assert models["base"]["status"] == "installed"
    local = models["local-lora-my-style"]
    assert (local["origin"], local["licence"]["id"], local["family_id"]) == (
        "local",
        "unknown",
        None,
    )
    # The file disappears: a catalogue model is available again, a local one is missing.
    (registry / "loras" / "my-style.safetensors").unlink()
    (registry / "checkpoints" / "base.safetensors").unlink()
    models = _models(client)
    assert (models["base"]["status"], models["local-lora-my-style"]["status"]) == (
        "available",
        "missing",
    )
    assert db.scalar(select(AuditEntry.action).where(AuditEntry.action == "models.rescanned"))


def test_wrong_size_is_flagged(client: TestClient, registry: Path) -> None:
    _put(registry, "checkpoints", "base.safetensors", b"truncated")
    assert _models(client)["base"]["verification"] == "mismatch"


def test_user_sets_the_family_of_a_local_model(client: TestClient, registry: Path) -> None:
    _put(registry, "loras", "mine.safetensors", b"x")
    client.post("/api/v1/models:rescan", headers=ORIGIN)
    r = client.patch("/api/v1/models/local-lora-mine", json={"family_id": "sdxl"}, headers=ORIGIN)
    assert r.json()["family_id"] == "sdxl"
    r = client.patch("/api/v1/models/base", json={"family_id": "sd15"}, headers=ORIGIN)
    assert r.json()["code"] == "MODEL_FROM_CATALOGUE"
    r = client.patch("/api/v1/models/local-lora-mine", json={"family_id": "sd15"}, headers=MCP)
    assert r.status_code == 403


# --- licences (FR-083, RULE-007, AC-008) -----------------------------------------------------


def test_ac008_licence_conflict_needs_an_audited_confirmation(
    client: TestClient, registry: Path, db: Session
) -> None:
    pid = _project(client, "commercial")
    lora = _models(client, project_id=pid)["lora15"]
    assert (lora["licence_conflict"], lora["licence_acknowledged"]) == (True, False)
    assert _models(client, project_id=pid)["base"]["licence_conflict"] is False
    check = client.post(
        "/api/v1/models:check", json={"model_ids": ["lora15"], "project_id": pid}, headers=ORIGIN
    ).json()
    assert check["licence_confirmation_required"] == ["lora15"]
    # Claude cannot confirm it; the user can, with a note.
    url = f"/api/v1/projects/{pid}/licence-acknowledgements"
    assert client.post(url, json={"model_id": "lora15"}, headers=MCP).status_code == 403
    r = client.post(url, json={"model_id": "lora15", "note": "client allows it"}, headers=ORIGIN)
    assert r.status_code == 201, r.text
    assert _models(client, project_id=pid)["lora15"]["licence_acknowledged"] is True
    entry = db.scalar(select(AuditEntry).where(AuditEntry.action == "licence.acknowledged"))
    assert entry is not None and entry.data["note"] == "client allows it"
    service.licence_gate(db, entry.project_id, ["lora15", "base"])  # no longer raises


def test_licence_gate_and_non_commercial_projects(
    client: TestClient, registry: Path, db: Session
) -> None:
    commercial = _project(client, "commercial")
    with pytest.raises(DomainError) as exc:
        service.licence_gate(db, uuid.UUID(commercial), ["lora15", "base"])
    assert (exc.value.code, exc.value.extra) == (
        "LICENCE_CONFIRMATION_REQUIRED",
        {"models": ["lora15"]},
    )
    hobby = _project(client, "non_commercial")
    assert _models(client, project_id=hobby)["lora15"]["licence_conflict"] is False
    r = client.post(
        f"/api/v1/projects/{hobby}/licence-acknowledgements",
        json={"model_id": "lora15"},
        headers=ORIGIN,
    )
    assert r.json()["code"] == "LICENCE_NO_CONFLICT"


# --- compatibility (FR-084, RULE-015) --------------------------------------------------------


def _codes(client: TestClient, ids: list[str]) -> list[str]:
    r = client.post("/api/v1/models:check", json={"model_ids": ids}, headers=ORIGIN)
    return [p["code"] for p in r.json()["problems"]]


def test_rule015_family_and_companion_checks(client: TestClient, registry: Path) -> None:
    for name, folder in (("base", "checkpoints"), ("lora15", "loras"), ("ipa", "ipadapter")):
        _put(registry, folder, f"{name}.safetensors", BLOB[name])
    assert _codes(client, ["base", "lora15"]) == ["FAMILY_MISMATCH"]
    assert _codes(client, ["base", "ipa"]) == ["CLIP_VISION_REQUIRED"]
    assert _codes(client, ["lora15"]) == ["CHECKPOINT_REQUIRED"]
    assert _codes(client, ["base", "ipa", "clip"]) == ["MODEL_NOT_INSTALLED"]
    _put(registry, "clip_vision", "clip.safetensors", BLOB["clip"])
    assert _codes(client, ["base", "ipa", "clip"]) == []


# --- downloads (FR-082, RULE-008, NFR-007) ---------------------------------------------------

CONFIRM = {
    "file_name": "base.safetensors",
    "source_url": "https://models.example/base.safetensors",
    "bytes": len(BLOB["base"]),
}


def _serve(body: bytes, *, ranges: bool = True, seen: list[str] | None = None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("range")
        if seen is not None:
            seen.append(rng or "")
        if rng and ranges:
            start = int(rng.removeprefix("bytes=").rstrip("-"))
            return httpx.Response(206, content=body[start:])
        return httpx.Response(200, content=body)

    service.set_http_client_factory(lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def _run(connection: Connection) -> None:
    handlers = {"download": service.handle_download, "verify_model": service.handle_verify_model}
    _runner(connection, handlers).tick()


def test_rule008_download_needs_the_users_exact_confirmation(
    client: TestClient, registry: Path
) -> None:
    url = "/api/v1/models/base:download"
    assert client.post(url, json=CONFIRM, headers=MCP).status_code == 403
    wrong = {**CONFIRM, "source_url": "https://elsewhere.example/base.safetensors"}
    r = client.post(url, json=wrong, headers=ORIGIN)
    assert (r.status_code, r.json()["code"]) == (409, "DOWNLOAD_CONFIRMATION_MISMATCH")
    assert r.json()["expected"] == CONFIRM
    r = client.post(url, json=CONFIRM, headers=ORIGIN)
    assert (r.status_code, r.json()["kind"]) == (202, "download")
    assert _models(client)["base"]["status"] == "downloading"
    again = client.post(url, json=CONFIRM, headers=ORIGIN)
    assert again.json()["code"] == "DOWNLOAD_IN_PROGRESS"


def test_fr082_download_verifies_and_installs(
    client: TestClient, registry: Path, connection: Connection
) -> None:
    _serve(BLOB["base"])
    job = client.post("/api/v1/models/base:download", json=CONFIRM, headers=ORIGIN).json()
    _run(connection)
    done = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert done["state"] == "completed", done
    assert (registry / "checkpoints" / "base.safetensors").read_bytes() == BLOB["base"]
    base = _models(client)["base"]
    assert (base["status"], base["verification"]) == ("installed", "ok")
    again = client.post("/api/v1/models/base:download", json=CONFIRM, headers=ORIGIN)
    assert again.json()["code"] == "MODEL_ALREADY_INSTALLED"


def test_nfr007_download_resumes_with_a_range(
    client: TestClient, registry: Path, connection: Connection
) -> None:
    half = len(BLOB["base"]) // 2
    _put(registry, "checkpoints", "base.safetensors.part", BLOB["base"][:half])
    seen: list[str] = []
    _serve(BLOB["base"], seen=seen)
    client.post("/api/v1/models/base:download", json=CONFIRM, headers=ORIGIN)
    _run(connection)
    assert seen == [f"bytes={half}-"]
    assert (registry / "checkpoints" / "base.safetensors").read_bytes() == BLOB["base"]
    assert not (registry / "checkpoints" / "base.safetensors.part").exists()


def test_server_without_ranges_restarts_the_download(
    client: TestClient, registry: Path, connection: Connection
) -> None:
    _put(registry, "checkpoints", "base.safetensors.part", b"stale bytes")
    _serve(BLOB["base"], ranges=False)
    client.post("/api/v1/models/base:download", json=CONFIRM, headers=ORIGIN)
    _run(connection)
    assert (registry / "checkpoints" / "base.safetensors").read_bytes() == BLOB["base"]


def test_tampered_download_is_discarded(
    client: TestClient, registry: Path, connection: Connection
) -> None:
    _serve(b"x" * len(BLOB["base"]))
    job = client.post("/api/v1/models/base:download", json=CONFIRM, headers=ORIGIN).json()
    _run(connection)
    done = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert (done["state"], done["error"]["code"]) == ("failed", "CHECKSUM_MISMATCH")
    assert list((registry / "checkpoints").iterdir()) == []
    assert _models(client)["base"]["status"] == "available"


def test_verify_job_checks_the_hash(
    client: TestClient, registry: Path, connection: Connection
) -> None:
    path = _put(registry, "checkpoints", "base.safetensors", BLOB["base"])
    job = client.post("/api/v1/models/base:verify", headers=ORIGIN)
    assert job.status_code == 202, job.text
    _run(connection)
    assert _models(client)["base"]["verification"] == "ok"
    path.write_bytes(bytes(reversed(BLOB["base"])))  # same size, different content
    client.post("/api/v1/models/base:verify", headers=ORIGIN)
    _run(connection)
    assert _models(client)["base"]["verification"] == "mismatch"
    missing = client.post("/api/v1/models/ipa:verify", headers=ORIGIN)
    assert missing.json()["code"] == "MODEL_NOT_INSTALLED"
