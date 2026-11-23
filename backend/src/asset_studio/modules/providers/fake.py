"""Fake engine for CI and UI work without a GPU (ADR-006, NFR-015)."""

import threading
import uuid
from dataclasses import dataclass, field

from asset_studio.modules.providers.base import (
    ENGINE_UNAVAILABLE,
    Capabilities,
    Device,
    EngineHealth,
    GenerationRequest,
    OutputFile,
    Progress,
    ProviderError,
)
from asset_studio.modules.providers.png import sample_image

MAX_SIDE = 1024
MAX_BATCH = 8


@dataclass
class _Job:
    width: int
    height: int
    seed: int
    batch: int
    polls: int = 0
    cancelled: bool = False
    outputs: list[OutputFile] = field(default_factory=list)


class FakeProvider:
    """Each ``progress`` call advances one step; after ``steps`` it completes (or fails
    with ``fail_with``). Images are small deterministic PNGs that depend on the seed."""

    name = "fake"

    def __init__(self, *, available: bool = True, steps: int = 3, fail_with: str | None = None):
        self.available = available
        self.steps = steps
        self.fail_with = fail_with
        self.freed = 0
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()

    def capabilities(self) -> Capabilities:
        return Capabilities("fake", frozenset({"text_to_image", "image_to_image", "pose"}))

    def health(self) -> EngineHealth:
        if not self.available:
            return EngineHealth(False, "fake", reason=ENGINE_UNAVAILABLE, detail="Fake engine off.")
        return EngineHealth(
            True, "fake", version="fake-1", devices=(Device("Fake GPU", 6144, 6144),)
        )

    def submit(self, request: GenerationRequest) -> str:
        if not self.available:
            raise ProviderError(ENGINE_UNAVAILABLE, "The fake engine is switched off.")
        request.workflow.render(request.inputs)  # same input validation as a real engine
        values = {name: spec.default for name, spec in request.workflow.inputs.items()}
        values.update(request.inputs)

        def size(key: str, default: int) -> int:
            value = values.get(key)
            return min(int(value), MAX_SIDE) if isinstance(value, int) and value > 0 else default

        job = _Job(
            width=size("width", 64),
            height=size("height", 64),
            seed=int(values.get("seed") or 0),
            batch=min(size("batch_size", 1), MAX_BATCH),
        )
        ref = uuid.uuid4().hex
        with self._lock:
            self._jobs[ref] = job
        return ref

    def _job(self, ref: str) -> _Job:
        with self._lock:
            job = self._jobs.get(ref)
        if job is None:
            raise ProviderError("ENGINE_JOB_UNKNOWN", "The engine does not know this job.")
        return job

    def progress(self, ref: str) -> Progress:
        job = self._job(ref)
        if job.cancelled:
            return Progress("failed", error="cancelled")
        job.polls += 1
        if job.polls <= self.steps:
            return Progress("running", step=job.polls, of=self.steps)
        if self.fail_with:
            return Progress("failed", error=self.fail_with)
        if not job.outputs:
            job.outputs = [
                OutputFile(
                    f"fake_{ref[:8]}_{i:02d}.png",
                    "image/png",
                    sample_image(job.width, job.height, job.seed + i),
                )
                for i in range(job.batch)
            ]
        return Progress("completed", step=self.steps, of=self.steps)

    def cancel(self, ref: str) -> None:
        self._job(ref).cancelled = True

    def collect(self, ref: str) -> list[OutputFile]:
        job = self._job(ref)
        if not job.outputs:
            raise ProviderError("ENGINE_JOB_NOT_FINISHED", "The job has no outputs yet.")
        return list(job.outputs)

    def free_vram(self) -> None:
        self.freed += 1
