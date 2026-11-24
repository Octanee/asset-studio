"""Training runs (ADR-011): validated specs only, fixed presets, one run at a time, progress
from the log, cancellation, and no paths in what leaves the agent."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from asset_studio_host_agent.app import AgentSettings, create_app
from asset_studio_host_agent.training import RunSpec, TrainingConfig, TrainingSupervisor, command

AUTH = {"Authorization": "Bearer secret-token"}


class FakeProc:
    """A kohya process: writes tqdm-like progress to the log and exits when told to."""

    def __init__(self, cmd: list[str], *, stdout: Any, **_: Any) -> None:
        self.cmd, self.log, self.code = cmd, stdout, None
        self.pid = 4242
        self.terminated = False
        out = Path(cmd[cmd.index("--output_dir") + 1])
        self.output = out / (cmd[cmd.index("--output_name") + 1] + ".safetensors")

    def step(self, done: int, total: int) -> None:
        pct = done * 100 // total
        bar = f"\rsteps:  {pct}%|{'█' * (pct // 10):<10}| {done}/{total} [00:01<00:02]"
        self.log.write(bar.encode())
        self.log.flush()

    def finish(self, code: int = 0) -> None:
        if code == 0:
            self.output.write_bytes(b"lora")
        self.code = code

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.terminated, self.code = True, 1

    def kill(self) -> None:
        self.code = -9

    def wait(self, timeout: float | None = None) -> int | None:
        return self.code


@pytest.fixture
def setup(tmp_path: Path) -> dict[str, Any]:
    kohya = tmp_path / "sd-scripts"
    for exe in ("Scripts/python.exe", "bin/python"):
        (kohya / ".venv" / exe).parent.mkdir(parents=True, exist_ok=True)
        (kohya / ".venv" / exe).write_text("")
    for script in ("train_network.py", "sdxl_train_network.py"):
        (kohya / script).write_text("")
    models = tmp_path / "models"
    (models / "checkpoints").mkdir(parents=True)
    (models / "checkpoints" / "v1-5-pruned-emaonly.safetensors").write_text("")
    exchange = tmp_path / "exchange"
    run_id = str(uuid.uuid4())
    images = exchange / run_id / "img" / "1_exz"
    images.mkdir(parents=True)
    (images / "001.png").write_bytes(b"png")
    procs: list[FakeProc] = []

    def spawn(cmd: list[str], **kw: Any) -> FakeProc:
        procs.append(FakeProc(cmd, **kw))
        return procs[-1]

    cfg = TrainingConfig(str(kohya), "", str(models), str(exchange))
    sup = TrainingSupervisor(cfg, spawn=spawn)
    app = create_app(AgentSettings(token="secret-token"), trainer=sup)
    return {"client": TestClient(app), "procs": procs, "run_id": run_id, "cfg": cfg}


def spec(run_id: str, **kw: Any) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "family": "sd15",
        "base_model": "v1-5-pruned-emaonly.safetensors",
        "output_name": "exz-plank",
        "resolution": 512,
        "max_train_steps": 100,
    } | kw


def test_specs_never_carry_paths_or_arguments(setup: dict[str, Any]) -> None:
    c, run_id = setup["client"], setup["run_id"]
    for bad in (
        {"base_model": "../secret.safetensors"},
        {"base_model": "checkpoints/x.safetensors"},
        {"base_model": "C:\\models\\x.safetensors"},
        {"output_name": "../out"},
        {"run_id": "../../windows"},
        {"family": "flux"},
        {"extra_args": "--some_flag"},
    ):
        r = c.post("/training-runs", json=spec(run_id) | bad, headers=AUTH)
        assert r.status_code == 422, bad
    assert c.post("/training-runs", json=spec(run_id)).status_code == 401


def test_presets_for_small_gpus() -> None:
    cfg = TrainingConfig("/k", "", "/m", "/x")
    run = Path("/x/r")
    sd15 = command(cfg, RunSpec.model_validate(spec(str(uuid.uuid4()))), run)
    assert sd15[1] == "train_network.py"
    assert sd15[sd15.index("--optimizer_type") + 1] == "AdamW8bit"
    assert "--gradient_checkpointing" not in sd15  # fits in 6 GB, 40% faster without
    xl_spec = spec(
        str(uuid.uuid4()), family="sdxl", resolution=768, vae="sdxl_vae_fp16fix.safetensors"
    )
    xl = command(cfg, RunSpec.model_validate(xl_spec), run)
    assert xl[1] == "sdxl_train_network.py"
    needed = {"--network_train_unet_only", "--cache_text_encoder_outputs", "--full_bf16"}
    assert needed | {"--gradient_checkpointing"} <= set(xl)
    assert xl[xl.index("--optimizer_type") + 1] == "Adafactor"
    assert xl[xl.index("--resolution") + 1] == "768,768"
    assert Path(xl[xl.index("--vae") + 1]) == Path("/m/vae/sdxl_vae_fp16fix.safetensors")


def test_a_run_reports_progress_and_its_output(setup: dict[str, Any]) -> None:
    c, run_id = setup["client"], setup["run_id"]
    r = c.post("/training-runs", json=spec(run_id), headers=AUTH)
    assert r.status_code == 200 and r.json()["state"] == "running"
    again = c.post("/training-runs", json=spec(run_id), headers=AUTH)
    assert again.json()["detail"]["code"] == "TRAINING_BUSY"
    proc = setup["procs"][0]
    # Caching bars come first and must not count as training steps.
    proc.log.write(b"\rcaching latents: 100%|##########| 10/10 [00:02<00:00]\n")
    s = c.get(f"/training-runs/{run_id}", headers=AUTH).json()
    assert (s["step"], s["total"]) == (0, 100)
    proc.step(40, 100)
    s = c.get(f"/training-runs/{run_id}", headers=AUTH).json()
    assert (s["state"], s["step"], s["total"]) == ("running", 40, 100)
    proc.step(100, 100)
    proc.finish(0)
    s = c.get(f"/training-runs/{run_id}", headers=AUTH).json()
    assert (s["state"], s["output"]) == ("completed", "exz-plank.safetensors")


def test_a_failure_reports_only_the_exit_code(setup: dict[str, Any]) -> None:
    c, run_id = setup["client"], setup["run_id"]
    c.post("/training-runs", json=spec(run_id), headers=AUTH)
    setup["procs"][0].finish(3)
    s = c.get(f"/training-runs/{run_id}", headers=AUTH).json()
    assert (s["state"], s["error"]) == ("failed", "kohya exited with code 3")
    assert str(Path(setup["cfg"].training_dir)) not in str(s)


def test_cancel_stops_the_process(setup: dict[str, Any]) -> None:
    c, run_id = setup["client"], setup["run_id"]
    c.post("/training-runs", json=spec(run_id), headers=AUTH)
    s = c.post(f"/training-runs/{run_id}:cancel", headers=AUTH).json()
    assert s["state"] == "cancelled" and setup["procs"][0].terminated


def test_inputs_must_exist(setup: dict[str, Any]) -> None:
    c = setup["client"]
    empty = str(uuid.uuid4())
    r = c.post("/training-runs", json=spec(empty), headers=AUTH)
    assert r.json()["detail"]["code"] == "TRAINING_INPUT_MISSING"
    missing = spec(setup["run_id"], base_model="nope.safetensors")
    r = c.post("/training-runs", json=missing, headers=AUTH)
    assert r.json()["detail"]["code"] == "TRAINING_INPUT_MISSING"
    r = c.get(f"/training-runs/{empty}", headers=AUTH)
    assert r.json()["detail"]["code"] == "TRAINING_RUN_NOT_FOUND"


def test_not_configured() -> None:
    c = TestClient(create_app(AgentSettings(token="secret-token")))
    r = c.post("/training-runs", json=spec(str(uuid.uuid4())), headers=AUTH)
    assert r.json()["detail"]["code"] == "TRAINING_NOT_CONFIGURED"
