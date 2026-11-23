"""Engine supervision and GPU probe (ADR-005, FR-043)."""

import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from asset_studio_host_agent import gpu
from asset_studio_host_agent.app import AgentSettings, create_app
from asset_studio_host_agent.engine import EngineConfig, EngineSupervisor

AUTH = {"Authorization": "Bearer secret-token"}


class FakeProc:
    pid = 4242

    def __init__(self) -> None:
        self.code: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        self.code = 0

    def kill(self) -> None:
        self.code = -9

    def wait(self, timeout: float | None = None) -> int | None:
        return self.code


class Spawner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.procs: list[FakeProc] = []

    def __call__(self, args: list[str], **kwargs: Any) -> FakeProc:
        self.calls.append((args, kwargs))
        self.procs.append(FakeProc())
        return self.procs[-1]


@pytest.fixture
def portable(tmp_path: Path) -> Path:
    root = tmp_path / "ComfyUI_windows_portable"
    (root / "python_embeded").mkdir(parents=True)
    (root / "python_embeded" / "python.exe").write_bytes(b"")
    (root / "ComfyUI").mkdir()
    (root / "ComfyUI" / "main.py").write_text("")
    return root


def _client(supervisor: EngineSupervisor, probe: Any = None) -> TestClient:
    settings = AgentSettings(token="secret-token")
    kwargs: dict[str, Any] = {"supervisor": supervisor}
    if probe is not None:
        kwargs["gpu_probe"] = probe
    return TestClient(create_app(settings, **kwargs))


def test_start_runs_the_pinned_command_on_loopback(portable: Path, tmp_path: Path) -> None:
    spawn = Spawner()
    sup = EngineSupervisor(EngineConfig(str(portable), log_dir=str(tmp_path / "logs")), spawn=spawn)
    status = _client(sup).post("/engine:start", headers=AUTH).json()
    assert (status["running"], status["pid"]) == (True, 4242)
    args, kwargs = spawn.calls[0]
    assert args[0].endswith("python.exe")
    assert args[1:3] == ["-s", str(portable / "ComfyUI" / "main.py")]
    assert args[args.index("--listen") + 1] == "127.0.0.1"
    assert kwargs["env"]["PYTHONUTF8"] == "1"
    assert "shell" not in kwargs
    assert (tmp_path / "logs" / "comfyui.log").exists()


def test_start_is_idempotent_and_stop_terminates(portable: Path, tmp_path: Path) -> None:
    spawn = Spawner()
    sup = EngineSupervisor(EngineConfig(str(portable), log_dir=str(tmp_path)), spawn=spawn)
    client = _client(sup)
    client.post("/engine:start", headers=AUTH)
    client.post("/engine:start", headers=AUTH)
    assert len(spawn.calls) == 1
    stopped = client.post("/engine:stop", headers=AUTH).json()
    assert spawn.procs[0].terminated and stopped["running"] is False
    assert stopped["exit_code"] == 0


def test_restart_starts_a_new_process(portable: Path, tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr("asset_studio_host_agent.engine.time.sleep", lambda _: None)
    spawn = Spawner()
    sup = EngineSupervisor(EngineConfig(str(portable), log_dir=str(tmp_path)), spawn=spawn)
    client = _client(sup)
    client.post("/engine:start", headers=AUTH)
    assert client.post("/engine:restart", headers=AUTH).json()["running"] is True
    assert len(spawn.calls) == 2 and spawn.procs[0].terminated


def test_stop_kills_a_process_that_ignores_terminate(portable: Path, tmp_path: Path) -> None:
    class Stubborn(FakeProc):
        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> int | None:
            if self.code is None:
                raise subprocess.TimeoutExpired("python", timeout or 0)
            return self.code

    proc = Stubborn()
    sup = EngineSupervisor(
        EngineConfig(str(portable), log_dir=str(tmp_path)), spawn=lambda *a, **k: proc
    )
    sup.start()
    assert sup.stop(timeout=0.01)["running"] is False
    assert proc.code == -9


def test_engine_not_configured_or_not_installed(tmp_path: Path) -> None:
    r = _client(EngineSupervisor(EngineConfig(""))).post("/engine:start", headers=AUTH)
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "ENGINE_NOT_CONFIGURED")
    r = _client(EngineSupervisor(EngineConfig(str(tmp_path)))).post("/engine:start", headers=AUTH)
    assert r.json()["detail"]["code"] == "ENGINE_NOT_INSTALLED"


def test_engine_endpoints_require_the_token(portable: Path) -> None:
    client = _client(EngineSupervisor(EngineConfig(str(portable)), spawn=Spawner()))
    for method, path in [("get", "/engine"), ("post", "/engine:start"), ("get", "/gpu")]:
        assert getattr(client, method)(path).status_code == 401


def test_gpu_probe_parses_nvidia_smi() -> None:
    out = "NVIDIA GeForce RTX 4060, 8188, 512, 3, 555.85\n"

    def run(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        assert args[1].startswith("--query-gpu=name,memory.total")
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    info = gpu.probe(run=run, which=lambda _: "nvidia-smi")
    assert info["available"] is True
    assert info["gpus"][0] == {
        "name": "NVIDIA GeForce RTX 4060",
        "memory_total_mb": 8188,
        "memory_used_mb": 512,
        "utilization_percent": 3,
        "driver": "555.85",
    }


def test_gpu_probe_without_nvidia_smi() -> None:
    info = gpu.probe(which=lambda _: None)
    assert (info["available"], info["reason"]) == (False, "NVIDIA_SMI_NOT_FOUND")
    assert gpu.parse("GPU, [N/A], 1, 2, 3")[0]["memory_total_mb"] is None


def test_gpu_endpoint(portable: Path) -> None:
    client = _client(
        EngineSupervisor(EngineConfig(str(portable))),
        probe=lambda: {"available": False, "reason": "NO_GPU", "gpus": []},
    )
    assert client.get("/gpu", headers=AUTH).json()["reason"] == "NO_GPU"
