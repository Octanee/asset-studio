"""Provider contracts (ADR-006). The domain talks to engines only through these types."""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from asset_studio.errors import DomainError
from asset_studio.modules.providers.workflows import WorkflowTemplate

ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"


class ProviderError(DomainError):
    """An engine refused or failed a request. ``code`` is stable and safe to show."""

    def __init__(self, code: str, detail: str, extra: dict[str, Any] | None = None):
        super().__init__(503 if code == ENGINE_UNAVAILABLE else 502, code, detail, extra)


@dataclass(frozen=True)
class Device:
    name: str
    vram_total_mb: int | None = None
    vram_free_mb: int | None = None


@dataclass(frozen=True)
class EngineHealth:
    available: bool
    engine: str
    version: str | None = None
    reason: str | None = None  # a stable code when not available, e.g. ENGINE_UNAVAILABLE
    detail: str | None = None
    devices: tuple[Device, ...] = ()


@dataclass(frozen=True)
class Capabilities:
    engine: str
    features: frozenset[str]


@dataclass(frozen=True)
class GenerationRequest:
    """What to run: a workflow version plus values for its declared inputs."""

    workflow: WorkflowTemplate
    inputs: dict[str, Any] = field(default_factory=dict)
    # Image inputs (PNG bytes) by input name: the provider uploads them and writes the
    # engine's file name into that input (pose skeleton, reference, init image).
    images: dict[str, bytes] = field(default_factory=dict)


ProgressState = Literal["queued", "running", "completed", "failed"]


@dataclass(frozen=True)
class Progress:
    state: ProgressState
    step: int | None = None
    of: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class OutputFile:
    filename: str
    mime: str
    data: bytes


class GenerationProvider(Protocol):
    """One image engine. Calls are blocking; the worker runs them on job threads."""

    name: str

    def capabilities(self) -> Capabilities: ...

    def health(self) -> EngineHealth: ...

    def submit(self, request: GenerationRequest) -> str:
        """Queue the request on the engine; returns the engine's reference."""
        ...

    def progress(self, ref: str) -> Progress: ...

    def cancel(self, ref: str) -> None: ...

    def collect(self, ref: str) -> list[OutputFile]: ...

    def free_vram(self) -> None:
        """Unload models so training can use the GPU (RULE-012)."""
        ...
