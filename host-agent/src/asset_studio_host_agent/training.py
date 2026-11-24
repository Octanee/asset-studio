"""LoRA training runs with kohya sd-scripts (ADR-011, WP-13).

A run is described by a validated spec; the agent builds the kohya command from it with
fixed presets for small GPUs (measured in the prototype). Requests never pass paths or
arguments: the dataset is the run's folder in the training exchange folder, written by the
worker, and the base model is a file name inside the model folder. Nothing runs through a
shell, and only one run at a time.
"""

import os
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from asset_studio_host_agent.engine import EngineError

FILE = r"[A-Za-z0-9][A-Za-z0-9 ._()+-]{0,200}\.safetensors"
# Only kohya's training bar ("steps: 12%|...| 48/400 ["), not the caching bars before it.
STEP = re.compile(rb"steps:\s+\d+%\|[^|\r\n]*\|\s*(\d+)/(\d+) \[")


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    family: Literal["sd15", "sdxl"]
    base_model: str = Field(pattern=f"^{FILE}$")  # a file in <models>/checkpoints
    vae: str | None = Field(default=None, pattern=f"^{FILE}$")  # a file in <models>/vae
    output_name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    resolution: Literal[512, 768, 1024]
    max_train_steps: int = Field(ge=1, le=20_000)
    network_dim: int = Field(default=16, ge=4, le=128)
    network_alpha: int = Field(default=8, ge=1, le=128)
    learning_rate: float = Field(default=1e-4, gt=0, le=1e-2)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)


@dataclass(frozen=True)
class TrainingConfig:
    sd_scripts_dir: str = ""
    python: str = ""  # default: <sd_scripts_dir>/.venv/Scripts/python.exe
    models_dir: str = ""  # the model folder shared with ComfyUI (checkpoints, vae, loras)
    training_dir: str = ""  # the exchange folder; the worker sees it as /training

    @property
    def configured(self) -> bool:
        return bool(self.sd_scripts_dir and self.models_dir and self.training_dir)

    def python_path(self) -> Path:
        if self.python:
            return Path(self.python)
        scripts = "Scripts" if sys.platform == "win32" else "bin"
        exe = "python.exe" if sys.platform == "win32" else "python"
        return Path(self.sd_scripts_dir) / ".venv" / scripts / exe


def command(cfg: TrainingConfig, spec: RunSpec, run_dir: Path) -> list[str]:
    """The kohya command for a spec: fixed presets, values only from the validated spec."""
    models = Path(cfg.models_dir)
    res = f"{spec.resolution},{spec.resolution}"
    common = [
        "--pretrained_model_name_or_path", str(models / "checkpoints" / spec.base_model),
        "--train_data_dir", str(run_dir / "img"),
        "--output_dir", str(run_dir / "out"),
        "--output_name", spec.output_name,
        "--save_model_as", "safetensors",
        "--caption_extension", ".txt",
        "--resolution", res,
        "--enable_bucket", "--min_bucket_reso", "256", "--max_bucket_reso", "1024",
        "--bucket_no_upscale",
        "--network_module", "networks.lora",
        "--network_dim", str(spec.network_dim),
        "--network_alpha", str(spec.network_alpha),
        "--learning_rate", str(spec.learning_rate),
        "--lr_scheduler", "constant",
        "--max_train_steps", str(spec.max_train_steps),
        "--train_batch_size", "1",
        "--mixed_precision", "bf16",
        "--save_precision", "fp16",
        "--cache_latents",
        "--sdpa",
        "--seed", str(spec.seed),
        "--max_data_loader_n_workers", "0",
    ]  # fmt: skip
    if spec.family == "sd15":
        # SD1.5 preset: AdamW8bit, 512 px, UNet and text encoder; it fits in 6 GB without
        # gradient checkpointing, which nearly doubles the time (about 0.8 s per step on 6 GB).
        return [
            str(cfg.python_path()), "train_network.py", *common,
            "--optimizer_type", "AdamW8bit",
            "--text_encoder_lr", str(spec.learning_rate / 2),
        ]  # fmt: skip
    # SDXL preset for small GPUs: UNet only, Adafactor, bf16, cached latents and text
    # encoder outputs, 768 px (about 30 s per step on 6 GB).
    sdxl = [
        str(cfg.python_path()), "sdxl_train_network.py", *common,
        "--network_train_unet_only",
        "--gradient_checkpointing",
        "--cache_text_encoder_outputs",
        "--optimizer_type", "Adafactor",
        "--optimizer_args", "scale_parameter=False", "relative_step=False", "warmup_init=False",
        "--max_grad_norm", "0",
        "--full_bf16",
        "--no_half_vae",
    ]  # fmt: skip
    if spec.vae:
        sdxl += ["--vae", str(models / "vae" / spec.vae)]
    return sdxl


Spawn = Callable[..., Any]


class TrainingSupervisor:
    def __init__(self, config: TrainingConfig, *, spawn: Spawn = subprocess.Popen) -> None:
        self.config = config
        self._spawn = spawn
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._proc: Any = None
        self._current: str | None = None
        self._log: IO[bytes] | None = None

    def _run_dir(self, run_id: str) -> Path:
        base = Path(self.config.training_dir).resolve()
        run_dir = (base / run_id).resolve()
        if base not in run_dir.parents:
            raise EngineError(422, "TRAINING_SPEC_INVALID", "Invalid run id.")
        return run_dir

    def _busy(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, spec: RunSpec) -> dict[str, Any]:
        with self._lock:
            cfg = self.config
            if not cfg.configured:
                raise EngineError(
                    409,
                    "TRAINING_NOT_CONFIGURED",
                    "kohya, the model folder or the exchange folder is not configured.",
                )
            script = "train_network.py" if spec.family == "sd15" else "sdxl_train_network.py"
            if not (cfg.python_path().is_file() and (Path(cfg.sd_scripts_dir) / script).is_file()):
                raise EngineError(
                    409, "TRAINING_NOT_INSTALLED", "kohya sd-scripts is not installed."
                )
            if self._busy():
                raise EngineError(409, "TRAINING_BUSY", "Another training run is in progress.")
            run_dir = self._run_dir(spec.run_id)
            images = run_dir / "img"
            if not images.is_dir() or not any(p.is_file() for p in images.rglob("*")):
                raise EngineError(
                    409, "TRAINING_INPUT_MISSING", "The run's dataset folder is empty."
                )
            models = Path(cfg.models_dir)
            needed = [models / "checkpoints" / spec.base_model]
            if spec.vae:
                needed.append(models / "vae" / spec.vae)
            if not all(p.is_file() for p in needed):
                raise EngineError(409, "TRAINING_INPUT_MISSING", "The base model file is missing.")
            (run_dir / "out").mkdir(parents=True, exist_ok=True)
            self._close_log()
            self._log = (run_dir / "train.log").open("ab")
            # Prototype S-3: UTF-8 console on Windows; no window for the child.
            env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            self._proc = self._spawn(
                command(cfg, spec, run_dir),
                cwd=cfg.sd_scripts_dir,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=flags,
            )
            self._current = spec.run_id
            self._runs[spec.run_id] = {
                "run_id": spec.run_id,
                "output_name": spec.output_name,
                "total": spec.max_train_steps,
                "started_at": datetime.now(UTC).isoformat(),
                "cancelled": False,
            }
            return self._status(spec.run_id)

    def _progress(self, run_id: str) -> tuple[int, int | None]:
        log = self._run_dir(run_id) / "train.log"
        try:
            with log.open("rb") as f:
                f.seek(max(0, log.stat().st_size - 16_384))
                tail = f.read()
        except OSError:
            return 0, None
        found = STEP.findall(tail)
        if not found:
            return 0, None
        done, total = found[-1]
        return int(done), int(total)

    def _status(self, run_id: str) -> dict[str, Any]:
        run = self._runs.get(run_id)
        if run is None:
            raise EngineError(404, "TRAINING_RUN_NOT_FOUND", "No such training run.")
        step, total = self._progress(run_id)
        current = run_id == self._current
        code = self._proc.poll() if current and self._proc is not None else run.get("exit_code")
        if current and code is not None:
            run["exit_code"] = code
            self._close_log()
        output = self._run_dir(run_id) / "out" / f"{run['output_name']}.safetensors"
        if code is None:
            state = "running"
        elif run["cancelled"]:
            state = "cancelled"
        elif code == 0 and output.is_file():
            state = "completed"
        else:
            state = "failed"
        return {
            "run_id": run_id,
            "state": state,
            "step": step,
            "total": total or run["total"],
            "exit_code": code,
            "started_at": run["started_at"],
            "output": output.name if state == "completed" else None,
            # The log stays on this computer; only the exit code leaves it.
            "error": f"kohya exited with code {code}" if state == "failed" else None,
        }

    def status(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return self._status(run_id)

    def cancel(self, run_id: str, timeout: float = 20.0) -> dict[str, Any]:
        with self._lock:
            if run_id not in self._runs:
                raise EngineError(404, "TRAINING_RUN_NOT_FOUND", "No such training run.")
            if run_id == self._current and self._busy():
                self._runs[run_id]["cancelled"] = True
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=timeout)
            return self._status(run_id)

    def stop(self) -> None:
        """On agent shutdown: do not leave a training process holding the GPU."""
        if self._current:
            self.cancel(self._current)

    def _close_log(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None
