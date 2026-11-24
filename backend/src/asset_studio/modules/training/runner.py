"""The ``train`` job (FR-072, FR-074, FR-075, ADR-011).

1. The run's images and captions are written to the training exchange folder, which the host
   agent's kohya reads (``<exchange>/<run id>/img/1_<trigger>/``).
2. The GPU is handed over: ComfyUI frees its VRAM and the host agent stops it.
3. kohya runs through the host agent from a validated spec; progress and cancellation follow.
4. The engine is started again, and the LoRA is copied into the shared model folder and
   registered with its family (FR-075), never overwriting a file.

With the fake engine (CI, UI work) a fake trainer stands in for kohya.
"""

import contextlib
import hashlib
import os
import shutil
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from asset_studio.config import get_settings
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import record
from asset_studio.modules.jobs.runner import Handler, JobCancelled, JobContext, WorkerStopping
from asset_studio.modules.models.models import Model
from asset_studio.modules.models.service import folder, get_model
from asset_studio.modules.providers.engine import EngineMonitor, get_engine_monitor
from asset_studio.modules.storage.local import get_storage
from asset_studio.modules.training import service
from asset_studio.modules.training.models import TrainingItem

POLL_SECONDS = 3.0


def exchange_root() -> Path:
    settings = get_settings()
    return Path(settings.training_dir or Path(settings.data_dir) / "training-exchange")


class Trainer(Protocol):
    def prepare(self) -> bool: ...

    def start(self, spec: dict[str, Any]) -> None: ...

    def status(self, run_id: str) -> dict[str, Any]: ...

    def cancel(self, run_id: str) -> None: ...

    def finish(self, restart_engine: bool) -> None: ...


class AgentTrainer:
    """kohya through the host agent; ComfyUI gives the GPU up for the run."""

    def __init__(self, monitor: EngineMonitor) -> None:
        if monitor.agent is None or not monitor.agent.configured:
            raise DomainError(
                409, "HOST_AGENT_NOT_CONFIGURED", "Training needs the host agent (run setup)."
            )
        self.monitor, self.agent = monitor, monitor.agent

    def prepare(self) -> bool:
        running = bool(self.agent.engine().get("running"))
        with contextlib.suppress(Exception):
            self.monitor.provider.free_vram()
        if running:
            self.agent.engine_action("stop")
            self.monitor.invalidate()
        return running

    def start(self, spec: dict[str, Any]) -> None:
        self.agent.training_start(spec)

    def status(self, run_id: str) -> dict[str, Any]:
        return self.agent.training_status(run_id)

    def cancel(self, run_id: str) -> None:
        with contextlib.suppress(DomainError):
            self.agent.training_cancel(run_id)

    def finish(self, restart_engine: bool) -> None:
        if restart_engine:
            with contextlib.suppress(DomainError):
                self.agent.engine_action("start")
            self.monitor.invalidate()


class FakeTrainer:
    """Stands in for kohya with the fake engine: a few progress steps, then a small file."""

    def __init__(self, root: Path, step_seconds: float = 0.2) -> None:
        self.root, self.step_seconds = root, step_seconds
        self.runs: dict[str, dict[str, Any]] = {}

    def prepare(self) -> bool:
        return False

    def start(self, spec: dict[str, Any]) -> None:
        self.runs[spec["run_id"]] = {"spec": spec, "polls": 0, "cancelled": False}

    def status(self, run_id: str) -> dict[str, Any]:
        run = self.runs[run_id]
        total = int(run["spec"]["max_train_steps"])
        run["polls"] += 1
        time.sleep(self.step_seconds)
        step = min(total, total * run["polls"] // 4)
        if run["cancelled"]:
            return {"state": "cancelled", "step": step, "total": total}
        if step < total:
            return {"state": "running", "step": step, "total": total}
        out = self.root / run_id / "out" / f"{run['spec']['output_name']}.safetensors"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake lora " + run_id.encode())
        return {"state": "completed", "step": total, "total": total}

    def cancel(self, run_id: str) -> None:
        self.runs[run_id]["cancelled"] = True

    def finish(self, restart_engine: bool) -> None:
        return None


@lru_cache
def _fake() -> FakeTrainer:
    return FakeTrainer(exchange_root())


def get_trainer() -> Trainer:
    if get_settings().engine_provider == "fake":
        return _fake()
    return AgentTrainer(get_engine_monitor())


def _write_dataset(run_dir: Path, trigger: str, items: list[TrainingItem]) -> int:
    """kohya's layout: a class folder ``<repeats>_<trigger>`` with images and .txt captions.
    The trigger word starts every caption, so the LoRA answers to it."""
    images = run_dir / "img" / f"1_{trigger}"
    if images.parent.exists():
        shutil.rmtree(images.parent)
    images.mkdir(parents=True)
    storage = get_storage()
    for n, item in enumerate(items, start=1):
        src = storage.path(item.storage_key)
        shutil.copyfile(src, images / f"{n:03d}{src.suffix.lower()}")
        caption = ", ".join(part for part in (trigger, item.caption.strip()) if part)
        (images / f"{n:03d}.txt").write_text(caption, encoding="utf-8")
    return len(items)


def _install(output: Path, name: str) -> tuple[Path, str, int]:
    """Copy the LoRA into the model folder (shared with ComfyUI) under a new name."""
    loras = folder("lora")
    loras.mkdir(parents=True, exist_ok=True)
    dest = loras / f"{name}.safetensors"
    if dest.exists():
        raise DomainError(409, "MODEL_FILE_EXISTS", "A model file with this name already exists.")
    tmp = loras / f".{name}.{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    try:
        with output.open("rb") as src, tmp.open("xb") as out:
            while chunk := src.read(1 << 20):
                digest.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest, digest.hexdigest(), dest.stat().st_size


def _follow(ctx: JobContext, trainer: Trainer, run_id: str) -> None:
    while True:
        try:
            status = trainer.status(run_id)
            ctx.progress(
                state="training", step=int(status.get("step") or 0), of=status.get("total")
            )
        except (JobCancelled, WorkerStopping):
            trainer.cancel(run_id)  # free the GPU: kohya must not keep running
            raise
        if status["state"] == "completed":
            return
        if status["state"] == "cancelled":
            raise JobCancelled
        if status["state"] == "failed":
            raise DomainError(
                500, "TRAINING_FAILED", str(status.get("error") or "Training failed.")
            )
        time.sleep(POLL_SECONDS)


def handle_train(ctx: JobContext) -> dict[str, Any]:
    run_id = uuid.UUID(ctx.params["run_id"])
    with ctx.runner.sessions() as s:
        run = service.get_run(s, run_id)
        dataset = service.get_dataset(s, run.dataset_id)
        items = service.list_items(s, dataset.id)
        base = get_model(s, run.base_model_id)
        vae = service.vae_for(s, run.family_id)
        trigger, family, name = dataset.trigger_word, run.family_id, run.output_name
        params, dataset_name, base_id = dict(run.params), dataset.name, run.base_model_id
        base_file, base_licence = base.file_name, base.licence_id
        vae_file = vae.file_name if vae else None
    run_dir = exchange_root() / str(run_id)
    ctx.progress(state="preparing", step=0, of=params["steps"])
    images = _write_dataset(run_dir, trigger, items)
    spec = {
        "run_id": str(run_id),
        "family": family,
        "base_model": base_file,
        "vae": vae_file,
        "output_name": name,
        "resolution": params["resolution"],
        "max_train_steps": params["steps"],
        "network_dim": params["network_dim"],
        "network_alpha": params["network_alpha"],
        "learning_rate": params["learning_rate"],
        "seed": params["seed"],
    }
    trainer = get_trainer()
    restart = trainer.prepare()
    try:
        trainer.start(spec)
        _follow(ctx, trainer, str(run_id))
    finally:
        trainer.finish(restart)
    output = run_dir / "out" / f"{name}.safetensors"
    if not output.is_file():
        raise DomainError(500, "TRAINING_OUTPUT_MISSING", "Training finished without a LoRA file.")
    dest, sha256, size = _install(output, name)
    model_id = f"lora-{name}"[:120]
    with ctx.runner.sessions() as s, s.begin():
        s.add(
            Model(
                id=model_id,
                name=f"{dataset_name} ({family.upper()} LoRA)",
                kind="lora",
                family_id=family,
                # A LoRA carries the terms of the model it was trained on.
                licence_id=base_licence,
                file_name=dest.name,
                sha256=sha256,
                bytes=size,
                file_bytes=size,
                origin="local",
                status="installed",
                verification="ok",
                notes=f"Trained in Asset Studio from {base_id} on '{dataset_name}'; "
                f"trigger word: {trigger}.",
            )
        )
        s.flush()
        row = service.get_run(s, run_id)
        row.output_model_id = model_id
        record(
            s,
            actor="system",
            action="training_run.completed",
            subject_type="training_run",
            subject_id=run_id,
            project_id=row.project_id,
            data={"model_id": model_id, "sha256": sha256, "bytes": size},
        )
    shutil.rmtree(run_dir / "img", ignore_errors=True)
    return {"model_id": model_id, "file": dest.name, "sha256": sha256, "images": images}


HANDLERS: dict[str, Handler] = {"train": handle_train}
