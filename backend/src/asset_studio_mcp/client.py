"""The REST API client used by the MCP tools.

The MCP server has no database or file access (ADR-008, MCP-Architecture). It forwards the
caller's MCP token to the API, which maps it to the actor ``mcp`` and enforces every rule
(RULE-004, RULE-005, RULE-010). An API problem becomes a tool error with its stable code, so
Claude sees why something was refused (FR-121).
"""

import base64
from collections.abc import Callable
from typing import Any

import httpx
from mcp.server.fastmcp.exceptions import ToolError

TokenSource = Callable[[], str]


class ApiError(ToolError):
    def __init__(self, status: int, code: str, detail: str, extra: dict[str, Any]) -> None:
        hint = {k: v for k, v in extra.items() if k not in ("type", "title", "status", "detail")}
        hint.pop("code", None)
        more = f" {hint}" if hint else ""
        super().__init__(f"{code} ({status}): {detail}{more}")
        self.status, self.code, self.extra = status, code, extra


class Api:
    def __init__(self, http: httpx.AsyncClient, token: TokenSource) -> None:
        self.http, self.token = http, token

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token()}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        content: bytes | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        response = await self.http.request(
            method,
            f"/api/v1{path}",
            params=query,
            json=json,
            content=content,
            headers=self._headers(idempotency_key),
        )
        if response.status_code >= 400:
            try:
                problem = response.json()
            except ValueError:
                problem = {}
            raise ApiError(
                response.status_code,
                str(problem.get("code", f"HTTP_{response.status_code}")),
                str(problem.get("detail", response.reason_phrase)),
                problem if isinstance(problem, dict) else {},
            )
        if response.status_code == 204 or not response.content:
            return None
        if response.headers.get("content-type", "").startswith("application/json"):
            data = response.json()
            # One JSON object per answer: a bare list would reach Claude as loose blocks.
            return {"items": data, "count": len(data)} if isinstance(data, list) else data
        return response.content

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, body: Any = None, **kw: Any) -> Any:
        return await self.request("POST", path, json=body, **kw)

    async def file(self, path: str, limit: int, **params: Any) -> tuple[bytes, str]:
        """A file's bytes and media type, refused above ``limit`` bytes."""
        query = {k: v for k, v in params.items() if v is not None}
        response = await self.http.get(f"/api/v1{path}", params=query, headers=self._headers())
        if response.status_code >= 400:
            problem = response.json() if response.content else {}
            raise ApiError(
                response.status_code,
                str(problem.get("code", f"HTTP_{response.status_code}")),
                str(problem.get("detail", response.reason_phrase)),
                problem,
            )
        if len(response.content) > limit:
            raise ToolError(f"FILE_TOO_LARGE: the image is over {limit // (1024 * 1024)} MB.")
        return response.content, response.headers.get("content-type", "image/webp")


def decode(data_base64: str, limit: int) -> bytes:
    try:
        data = base64.b64decode(data_base64, validate=True)
    except ValueError as exc:
        raise ToolError("BASE64_INVALID: the data is not valid base64.") from exc
    if len(data) > limit:
        raise ToolError(f"FILE_TOO_LARGE: at most {limit // (1024 * 1024)} MB.")
    return data
