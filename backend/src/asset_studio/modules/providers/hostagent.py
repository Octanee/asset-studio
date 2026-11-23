"""Client of the native host agent (ADR-005): engine start/stop and GPU information.

The agent listens on the host's loopback with a per-install token; containers reach it as
``host.docker.internal``. Every failure becomes a stable problem code.
"""

from typing import Any, Literal

import httpx

from asset_studio.errors import DomainError

EngineAction = Literal["start", "stop", "restart"]


class HostAgentClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.token = token
        # Starting or stopping the engine can take a while; reads stay quick.
        self.http = client or httpx.Client(base_url=base_url, timeout=timeout)

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _call(self, method: str, path: str, timeout: float | None = None) -> Any:
        if not self.configured:
            raise DomainError(
                409, "HOST_AGENT_NOT_CONFIGURED", "The host agent token is not set (run setup)."
            )
        kwargs: dict[str, Any] = {"headers": {"Authorization": f"Bearer {self.token}"}}
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            response = self.http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise DomainError(
                503, "HOST_AGENT_UNAVAILABLE", "The host agent is not running."
            ) from exc
        if response.status_code == 401:
            raise DomainError(502, "HOST_AGENT_REJECTED", "The host agent rejected the token.")
        if response.status_code >= 400:
            body = _safe_json(response)
            detail = body.get("detail") if isinstance(body, dict) else None
            if isinstance(detail, dict) and "code" in detail:
                raise DomainError(
                    response.status_code, str(detail["code"]), str(detail.get("detail", ""))
                )
            raise DomainError(
                502, "HOST_AGENT_ERROR", f"The host agent answered {response.status_code}."
            )
        return response.json()

    def health(self) -> dict[str, Any]:
        return dict(self._call("GET", "/health"))

    def gpu(self) -> dict[str, Any]:
        return dict(self._call("GET", "/gpu"))

    def engine(self) -> dict[str, Any]:
        return dict(self._call("GET", "/engine"))

    def engine_action(self, action: EngineAction) -> dict[str, Any]:
        return dict(self._call("POST", f"/engine:{action}", timeout=60.0))


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {}
