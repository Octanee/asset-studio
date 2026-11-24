"""LoRAs in generation (WP-13 part 2): workflow templates chain LoRAs after the checkpoint,
styles and characters link LoRAs (FR-016, FR-075), generation uses them with their trigger
words and the same family as the checkpoint (RULE-015), and versions record them (RULE-011)."""

import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.modules.assets.models import AssetVersion
from asset_studio.modules.models.models import Model
from asset_studio.modules.models.service import sync_catalogue
from asset_studio.modules.projects.models import Project
from asset_studio.modules.providers.fake import FakeProvider
from asset_studio.modules.training.models import TrainingDataset, TrainingRun
from asset_studio.modules.workflows.builtin import Features, template
from tests.conftest import MCP, ORIGIN
from tests.test_generation import (  # noqa: F401 - fixtures used by name
    _project,
    _run,
    _spec,
    _style_character,
    api,
    engine,
    installed,
)


def test_templates_chain_loras_after_the_checkpoint() -> None:
    t = template(Features(reference=True, loras=2))
    assert t.id == "txt2img+reference+lora2"
    g = t.graph
    assert g["40"]["inputs"]["model"] == ["1", 0] and g["41"]["inputs"]["clip"] == ["40", 1]
    # The prompts, the sampler and the IP-Adapter all take the last LoRA's outputs.
    assert g["3"]["inputs"]["clip"] == ["41", 1] and g["4"]["inputs"]["clip"] == ["41", 1]
    assert g["23"]["inputs"]["model"] == ["41", 0]
    assert template(Features(loras=1)).graph["6"]["inputs"]["model"] == ["40", 0]
    assert template(Features()).graph["6"]["inputs"]["model"] == ["1", 0]
    rendered = template(Features(loras=1)).render(
        {
            "checkpoint": "c",
            "prompt": "p",
            "seed": 1,
            "steps": 4,
            "cfg": 5.0,
            "sampler": "euler",
            "scheduler": "normal",
            "width": 512,
            "height": 512,
            "lora_1": "exz.safetensors",
            "lora_1_strength": 0.7,
        }
    )
    lora = rendered["40"]["inputs"]
    assert (lora["lora_name"], lora["strength_model"], lora["strength_clip"]) == (
        "exz.safetensors",
        0.7,
        0.7,
    )


def test_plans_queued_before_loras_still_load() -> None:
    """Jobs queued before WP-13 part 2 have no "loras" in their features or plan."""
    assert Features(img2img=False, pose=False, reference=False, vae=False).loras == 0


def _lora(db: Session, root: Path, family: str, trigger: str | None = None) -> str:
    sync_catalogue(db)  # the families come from the catalogue
    model_id = f"lora-test-{family}-{uuid.uuid4().hex[:6]}"
    (root / "loras").mkdir(parents=True, exist_ok=True)
    (root / "loras" / f"{model_id}.safetensors").write_bytes(b"lora")
    db.add(
        Model(
            id=model_id,
            name=f"Test {family} LoRA",
            kind="lora",
            family_id=family,
            licence_id="mit",
            file_name=f"{model_id}.safetensors",
            origin="local",
            status="installed",
            file_bytes=4,
            verification="ok",
        )
    )
    db.flush()
    if trigger:
        project = db.scalars(select(Project).order_by(Project.created_at.desc())).first()
        assert project is not None
        dataset = TrainingDataset(project_id=project.id, name="Ola", trigger_word=trigger)
        db.add(dataset)
        db.flush()
        db.add(
            TrainingRun(
                project_id=project.id,
                dataset_id=dataset.id,
                family_id=family,
                base_model_id="xl",
                params={},
                images=5,
                estimate={},
                output_name=model_id,
                output_model_id=model_id,
                created_by_actor="user",
            )
        )
    db.commit()
    return model_id


def test_fr075_styles_and_characters_link_loras(
    api: TestClient, installed: Path, db: Session
) -> None:
    pid = _project(api)
    style, character = _style_character(api, pid)
    lora = _lora(db, installed, "sdxl", trigger="ola_woman")
    r = api.put(
        f"/api/v1/characters/{character}/loras/{lora}", json={"strength": 0.7}, headers=ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json() == [
        {
            "model_id": lora,
            "name": "Test sdxl LoRA",
            "family_id": "sdxl",
            "status": "installed",
            "strength": 0.7,
            "trigger_word": "ola_woman",
        }
    ]
    # Claude may link LoRAs too: it is configuration, not a decision (RULE-005).
    r = api.put(f"/api/v1/styles/{style}/loras/{lora}", json={"strength": 0.5}, headers=MCP)
    assert r.json()[0]["strength"] == 0.5
    not_lora = api.put(f"/api/v1/styles/{style}/loras/xl", json={}, headers=ORIGIN)
    assert not_lora.json()["code"] == "MODEL_KIND_WRONG"
    second = _lora(db, installed, "sdxl")
    third = _lora(db, installed, "sdxl")
    assert api.put(f"/api/v1/styles/{style}/loras/{second}", json={}, headers=ORIGIN).is_success
    limit = api.put(f"/api/v1/styles/{style}/loras/{third}", json={}, headers=ORIGIN)
    assert limit.json()["code"] == "LORA_LIMIT"
    r = api.delete(f"/api/v1/styles/{style}/loras/{lora}", headers=ORIGIN)
    assert [x["model_id"] for x in r.json()] == [second]


def test_fr075_rule015_generation_uses_linked_loras_with_their_trigger_word(
    api: TestClient, installed: Path, db: Session
) -> None:
    pid = _project(api)
    _, character = _style_character(api, pid)
    lora = _lora(db, installed, "sdxl", trigger="ola_woman")
    api.put(f"/api/v1/characters/{character}/loras/{lora}", json={"strength": 0.7}, headers=ORIGIN)
    spec = _spec(pid, character_id=character)
    c = api.post("/api/v1/generations:check", json=spec, headers=ORIGIN).json()
    assert c["ready"] is True, c["problems"]
    assert c["models"]["lora_1"] == lora and c["workflow"]["id"].endswith("+lora")
    assert c["prompts"][0].startswith("ola_woman, doing a squat")
    # RULE-015: an SD1.5 LoRA does not fit an SDXL checkpoint.
    sd15 = _lora(db, installed, "sd15")
    wrong_spec = _spec(pid, loras=[{"model_id": sd15, "strength": 1.0}])
    wrong = api.post("/api/v1/generations:check", json=wrong_spec, headers=ORIGIN).json()
    assert [p["code"] for p in wrong["problems"]] == ["FAMILY_MISMATCH"]
    three = _spec(pid, loras=[{"model_id": "a"}, {"model_id": "b"}, {"model_id": "c"}])
    assert api.post("/api/v1/generations:check", json=three, headers=ORIGIN).status_code == 422


def test_rule011_versions_record_the_loras(
    api: TestClient, engine: FakeProvider, installed: Path, connection: Connection, db: Session
) -> None:
    pid = _project(api)
    lora = _lora(db, installed, "sdxl", trigger="ola_woman")
    spec = _spec(pid, loras=[{"model_id": lora, "strength": 0.6}])
    q = api.post("/api/v1/generations", json=spec, headers=ORIGIN)
    assert q.status_code == 202, q.text
    _run(connection)
    db.expire_all()
    asset_id = uuid.UUID(q.json()["asset_ids"][0])
    version = db.scalars(select(AssetVersion).where(AssetVersion.asset_id == asset_id)).one()
    meta: dict[str, Any] = version.generation_metadata
    assert meta["workflow"]["id"] == "txt2img+vae+lora"
    assert [(x["id"], x["strength"], x["trigger_word"]) for x in meta["loras"]] == [
        (lora, 0.6, "ola_woman")
    ]
    assert meta["prompt"].startswith("ola_woman, ")
