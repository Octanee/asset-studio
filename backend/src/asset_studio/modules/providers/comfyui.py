"""ComfyUI adapter over its HTTP API (ADR-006, NFR-008).

Endpoints used: ``/system_stats`` (health), ``/prompt`` (submit), ``/history/{id}`` and
``/queue`` (progress), ``/queue`` delete and ``/interrupt`` (cancel), ``/view`` (outputs),
``/free`` (unload models). Step-level progress over the ``/ws`` socket arrives with the
Generation Studio (WP-08); until then progress is the queue position and completion.
"""

import mimetypes
import uuid
from typing import Any

import httpx

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

MB = 1024 * 1024


class ComfyUIProvider:
    name = "comfyui"

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
        health_timeout: float = 2.0,
    ) -> None:
        self.http = client or httpx.Client(base_url=base_url, timeout=timeout)
        self.health_timeout = health_timeout
        self.client_id = uuid.uuid4().hex

    def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self.http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ProviderError(ENGINE_UNAVAILABLE, "ComfyUI is not reachable.") from exc

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._call(method, path, **kwargs)
        if response.status_code >= 400:
            raise ProviderError(
                "ENGINE_ERROR",
                f"ComfyUI answered {response.status_code} to {path}.",
                {"status": response.status_code},
            )
        return response.json()

    def capabilities(self) -> Capabilities:
        return Capabilities(
            "comfyui", frozenset({"text_to_image", "image_to_image", "pose", "background_removal"})
        )

    def health(self) -> EngineHealth:
        try:
            stats = self._json("GET", "/system_stats", timeout=self.health_timeout)
            system = stats.get("system", {})
            devices = tuple(
                Device(
                    str(d.get("name", "unknown")),
                    int(d["vram_total"]) // MB if d.get("vram_total") is not None else None,
                    int(d["vram_free"]) // MB if d.get("vram_free") is not None else None,
                )
                for d in stats.get("devices", [])
            )
            return EngineHealth(
                True, "comfyui", version=system.get("comfyui_version"), devices=devices
            )
        except (ProviderError, ValueError, TypeError, AttributeError) as exc:
            detail = exc.detail if isinstance(exc, ProviderError) else "Unexpected answer."
            return EngineHealth(False, "comfyui", reason=ENGINE_UNAVAILABLE, detail=detail)

    def submit(self, request: GenerationRequest) -> str:
        graph = request.workflow.render(request.inputs)
        response = self._call(
            "POST", "/prompt", json={"prompt": graph, "client_id": self.client_id}
        )
        if response.status_code == 400:
            body = _safe_json(response)
            error = body.get("error", {}) if isinstance(body, dict) else {}
            nodes = body.get("node_errors", {}) if isinstance(body, dict) else {}
            raise ProviderError(
                "ENGINE_REJECTED",
                str(error.get("message") or "ComfyUI rejected the workflow.")[:500],
                {"workflow": request.workflow.id, "nodes": sorted(nodes)[:20]},
            )
        if response.status_code >= 400:
            raise ProviderError("ENGINE_ERROR", f"ComfyUI answered {response.status_code}.")
        return str(response.json()["prompt_id"])

    def _entry(self, ref: str) -> dict[str, Any] | None:
        history = self._json("GET", f"/history/{ref}")
        entry = history.get(ref) if isinstance(history, dict) else None
        return entry if isinstance(entry, dict) else None

    def progress(self, ref: str) -> Progress:
        entry = self._entry(ref)
        if entry is not None:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                return Progress("failed", error=_error_message(status))
            if status.get("completed") or entry.get("outputs"):
                return Progress("completed")
        queue = self._json("GET", "/queue")
        if ref in _ids(queue.get("queue_running", [])):
            return Progress("running")
        if ref in _ids(queue.get("queue_pending", [])):
            return Progress("queued")
        if entry is not None:
            return Progress("running")
        return Progress("failed", error="The engine no longer knows this job (restarted?).")

    def cancel(self, ref: str) -> None:
        queue = self._json("GET", "/queue")
        if ref in _ids(queue.get("queue_pending", [])):
            self._call("POST", "/queue", json={"delete": [ref]})
        if ref in _ids(queue.get("queue_running", [])):
            # One GPU job at a time (RULE-012), so the running prompt is ours.
            self._call("POST", "/interrupt", json={"prompt_id": ref})

    def collect(self, ref: str) -> list[OutputFile]:
        entry = self._entry(ref)
        if entry is None:
            raise ProviderError("ENGINE_JOB_NOT_FINISHED", "The job has no outputs yet.")
        files: list[OutputFile] = []
        for node in sorted(entry.get("outputs", {})):
            for image in entry["outputs"][node].get("images", []):
                if image.get("type") != "output":
                    continue  # previews and temp files are not results
                params = {
                    "filename": image["filename"],
                    "subfolder": image.get("subfolder", ""),
                    "type": "output",
                }
                response = self._call("GET", "/view", params=params)
                if response.status_code >= 400:
                    raise ProviderError("ENGINE_ERROR", "ComfyUI could not return an output.")
                mime = response.headers.get("content-type", "").split(";")[0] or (
                    mimetypes.guess_type(image["filename"])[0] or "application/octet-stream"
                )
                files.append(OutputFile(image["filename"], mime, response.content))
        return files

    def free_vram(self) -> None:
        self._call("POST", "/free", json={"unload_models": True, "free_memory": True})


def _ids(items: list[Any]) -> set[str]:
    return {str(item[1]) for item in items if isinstance(item, list) and len(item) > 1}


def _error_message(status: dict[str, Any]) -> str:
    for message in status.get("messages", []):
        if isinstance(message, list) and len(message) == 2 and message[0] == "execution_error":
            data = message[1] if isinstance(message[1], dict) else {}
            return str(data.get("exception_message") or "Execution failed.")[:500]
    return "Execution failed."


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {}
