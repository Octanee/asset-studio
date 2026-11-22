"""Session bootstrap for the single local user (D-29, ADR-012)."""

from fastapi import APIRouter, Response
from pydantic import BaseModel

from asset_studio.api.security import SESSION_COOKIE, session_value
from asset_studio.config import get_settings
from asset_studio.errors import DomainError

router = APIRouter()


class SessionInfo(BaseModel):
    actor: str


@router.get("", response_model=SessionInfo)
def start_session(response: Response) -> SessionInfo:
    """Sets the session cookie. Reachable only through an allowed Host (loopback)."""
    settings = get_settings()
    if not settings.session_secret:
        raise DomainError(503, "NOT_CONFIGURED", "Run setup first: the session secret is missing.")
    response.set_cookie(
        SESSION_COOKIE, session_value(settings), httponly=True, samesite="strict", path="/api"
    )
    return SessionInfo(actor="user")
