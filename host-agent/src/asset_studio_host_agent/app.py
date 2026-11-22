"""Host agent HTTP API. Engine control and training endpoints arrive in WP-05 and WP-13.

The API is deliberately narrow: fixed endpoints, no shell, loopback only, token required.
"""

import hmac

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic_settings import BaseSettings, SettingsConfigDict

from asset_studio_host_agent import __version__


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASSET_STUDIO_AGENT_", env_file=".env", extra="ignore"
    )

    host: str = "127.0.0.1"
    port: int = 8410
    token: str = ""


def create_app(settings: AgentSettings | None = None) -> FastAPI:
    cfg = settings or AgentSettings()
    app = FastAPI(title="Asset Studio host agent", version=__version__)

    def require_token(authorization: str = Header(default="")) -> None:
        expected = f"Bearer {cfg.token}"
        if not cfg.token or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing token")

    @app.get("/health", dependencies=[Depends(require_token)])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


def main() -> None:
    import uvicorn

    cfg = AgentSettings()
    if cfg.host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("The host agent only listens on loopback (ADR-012).")
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
