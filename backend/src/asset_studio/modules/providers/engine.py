"""Engine status, the GPU-lane gate (RULE-013, FR-043) and the generation driver."""

import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from functools import lru_cache
from typing import Any, Protocol

from asset_studio.config import Settings, get_settings
from asset_studio.errors import DomainError
from asset_studio.modules.providers.base import (
    ENGINE_UNAVAILABLE,
    EngineHealth,
    GenerationProvider,
    GenerationRequest,
    OutputFile,
    ProviderError,
)
from asset_studio.modules.providers.comfyui import ComfyUIProvider
from asset_studio.modules.providers.fake import FakeProvider
from asset_studio.modules.providers.hostagent import EngineAction, HostAgentClient


class EngineMonitor:
    """Caches engine health briefly: the worker asks on every scheduling round."""

    def __init__(
        self,
        provider: GenerationProvider,
        agent: HostAgentClient | None = None,
        *,
        ttl: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.provider, self.agent, self.ttl, self.clock = provider, agent, ttl, clock
        self._cached: tuple[float, EngineHealth] | None = None
        self._lock = threading.Lock()

    def health(self, *, fresh: bool = False) -> EngineHealth:
        with self._lock:
            now = self.clock()
            if fresh or self._cached is None or now - self._cached[0] >= self.ttl:
                self._cached = (now, self.provider.health())
            return self._cached[1]

    def invalidate(self) -> None:
        with self._lock:
            self._cached = None

    def gate(self) -> str | None:
        """Lane gate for the GPU lane: None when jobs may start, else the reason."""
        health = self.health()
        return None if health.available else (health.reason or ENGINE_UNAVAILABLE)

    def status(self) -> dict[str, Any]:
        health = self.health(fresh=True)
        agent: dict[str, Any] = {"configured": bool(self.agent and self.agent.configured)}
        if self.agent is not None and self.agent.configured:
            try:
                agent.update(reachable=True, engine=self.agent.engine(), gpu=self.agent.gpu())
            except DomainError as exc:
                agent.update(reachable=False, reason=exc.code)
        return {
            "provider": self.provider.name,
            **asdict(health),
            "features": sorted(self.provider.capabilities().features),
            "agent": agent,
        }

    def control(self, action: EngineAction) -> dict[str, Any]:
        if self.agent is None:
            raise DomainError(409, "HOST_AGENT_NOT_CONFIGURED", "No host agent is configured.")
        result = self.agent.engine_action(action)
        self.invalidate()
        return result


def build_provider(settings: Settings) -> GenerationProvider:
    if settings.engine_provider == "fake":
        return FakeProvider()
    return ComfyUIProvider(settings.comfyui_url)


@lru_cache
def get_engine_monitor() -> EngineMonitor:
    settings = get_settings()
    agent = HostAgentClient(settings.host_agent_url, settings.host_agent_token)
    return EngineMonitor(build_provider(settings), agent, ttl=settings.engine_health_ttl_seconds)


class ProgressSink(Protocol):
    """What a job offers a long call: progress reports and a cancellation check.
    The worker's ``JobContext`` fits this."""

    def progress(self, **data: Any) -> None: ...

    def check(self) -> None: ...


def run_generation(
    provider: GenerationProvider,
    request: GenerationRequest,
    sink: ProgressSink,
    *,
    poll_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[OutputFile]:
    """Submit, follow and collect one request. If the job is cancelled or the worker stops
    (``sink`` raises), the engine job is cancelled too before the exception propagates."""
    ref = provider.submit(request)
    last: tuple[Any, ...] | None = None
    try:
        while True:
            sink.check()
            p = provider.progress(ref)
            if p.state == "completed":
                return provider.collect(ref)
            if p.state == "failed":
                raise ProviderError("GENERATION_FAILED", p.error or "The engine failed.")
            current = (p.state, p.step, p.of)
            if current != last:
                sink.progress(engine_state=p.state, step=p.step, of=p.of)
                last = current
            sleep(poll_seconds)
    except ProviderError:
        raise
    except Exception:
        with contextlib.suppress(ProviderError):  # the engine is gone; nothing to cancel
            provider.cancel(ref)
        raise
