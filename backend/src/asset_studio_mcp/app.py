"""The MCP server as a web app: Streamable HTTP at ``/mcp`` (MCP-Architecture).

Claude Code connects with the per-install MCP token as a bearer token; the server forwards it
to the API with every call. Requests without a token are refused before any tool runs.
"""

import os
from typing import Any

import httpx
from mcp.server.fastmcp.exceptions import ToolError
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from asset_studio_mcp.client import Api
from asset_studio_mcp.server import Ctx, build

API_URL = os.environ.get("ASSET_STUDIO_MCP_API_URL", "http://127.0.0.1:8400")
BIND = os.environ.get("ASSET_STUDIO_MCP_BIND", "127.0.0.1")
PORT = int(os.environ.get("ASSET_STUDIO_MCP_PORT", "8411"))


def bearer(request: Request | None) -> str | None:
    header = request.headers.get("authorization", "") if request is not None else ""
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


class BearerRequired(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith("/mcp") and bearer(request) is None:
            return JSONResponse(
                {"error": "unauthorized", "detail": "Send the MCP token as a bearer token."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)


def create_app(http: httpx.AsyncClient | None = None) -> Starlette:
    client = http or httpx.AsyncClient(base_url=API_URL, timeout=60.0)

    def api_for(ctx: Ctx) -> Api:
        request: Any = ctx.request_context.request
        token = bearer(request)
        if token is None:
            raise ToolError("UNAUTHENTICATED: send the MCP token as a bearer token.")
        return Api(client, lambda: token)

    app = build(api_for, host=BIND, port=PORT).streamable_http_app()
    app.add_middleware(BearerRequired)
    return app
