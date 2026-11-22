"""Request security (ADR-012): Host allow-list, Origin checks and actor resolution.

The actor is derived from the credential, never from a request field:
- bearer MCP token -> ``mcp``; bearer worker token -> ``system``;
- session cookie (set by ``GET /api/v1/session`` on the same origin) -> ``user``.
"""

import hashlib
import hmac
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from asset_studio.config import Settings, get_settings
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import Actor

SESSION_COOKIE = "asset_studio_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _host_only(value: str) -> str:
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def session_value(settings: Settings) -> str:
    return hmac.new(
        settings.session_secret.encode(), b"asset-studio-user", hashlib.sha256
    ).hexdigest()


class HostOriginMiddleware(BaseHTTPMiddleware):
    """Rejects requests for unknown Host names (DNS rebinding) before routing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        host = _host_only(request.headers.get("host", ""))
        if host not in settings.allowed_hosts:
            from asset_studio.api.problems import problem_response

            return problem_response(400, "HOST_NOT_ALLOWED", "This host name is not allowed.")
        return await call_next(request)


def resolve_actor(request: Request) -> Actor:
    settings = get_settings()
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        if settings.mcp_token and hmac.compare_digest(token, settings.mcp_token):
            return "mcp"
        if settings.worker_token and hmac.compare_digest(token, settings.worker_token):
            return "system"
        raise DomainError(401, "AUTH_INVALID", "The token is not valid.")
    cookie = request.cookies.get(SESSION_COOKIE, "")
    if settings.session_secret and cookie and hmac.compare_digest(cookie, session_value(settings)):
        if request.method in UNSAFE:
            origin = request.headers.get("origin")
            if not origin or _host_only(urlsplit(origin).netloc) not in settings.allowed_hosts:
                raise DomainError(403, "ORIGIN_NOT_ALLOWED", "Request origin is not allowed.")
        return "user"
    raise DomainError(401, "AUTH_REQUIRED", "Open the app from this computer to start a session.")


CurrentActor = Annotated[Actor, Depends(resolve_actor)]
