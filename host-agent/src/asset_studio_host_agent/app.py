"""Host agent HTTP API (ADR-005): the engine (WP-05) and LoRA training runs (WP-13).

The API is deliberately narrow: fixed endpoints, no shell, loopback only, token required.
"""

import hmac
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic_settings import BaseSettings, SettingsConfigDict

from asset_studio_host_agent import __version__, gpu
from asset_studio_host_agent.engine import EngineConfig, EngineError, EngineSupervisor
from asset_studio_host_agent.training import RunSpec, TrainingConfig, TrainingSupervisor


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASSET_STUDIO_AGENT_", env_file=".env", extra="ignore"
    )

    host: str = "127.0.0.1"
    port: int = 8410
    token: str = ""
    # ComfyUI portable build (pinned version, installed by setup in WP-17).
    comfyui_dir: str = ""
    comfyui_python: str = ""
    comfyui_port: int = 8188
    log_dir: str = "./logs"
    # kohya sd-scripts with its own Python 3.11 venv (ADR-011), the model folder shared with
    # ComfyUI and the training exchange folder (the worker's /training).
    kohya_dir: str = ""
    kohya_python: str = ""
    models_dir: str = ""
    training_dir: str = ""


def create_app(
    settings: AgentSettings | None = None,
    *,
    supervisor: EngineSupervisor | None = None,
    gpu_probe: Callable[[], dict[str, Any]] = gpu.probe,
    trainer: TrainingSupervisor | None = None,
) -> FastAPI:
    cfg = settings or AgentSettings()
    engine = supervisor or EngineSupervisor(
        EngineConfig(cfg.comfyui_dir, cfg.comfyui_python, cfg.comfyui_port, cfg.log_dir)
    )

    training = trainer or TrainingSupervisor(
        TrainingConfig(cfg.kohya_dir, cfg.kohya_python, cfg.models_dir, cfg.training_dir)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        training.stop()  # children of the agent: do not leave them holding the GPU
        engine.stop()

    app = FastAPI(title="Asset Studio host agent", version=__version__, lifespan=lifespan)

    def require_token(authorization: str = Header(default="")) -> None:
        expected = f"Bearer {cfg.token}"
        if not cfg.token or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing token")

    def run(action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return action()
        except EngineError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "detail": exc.detail}) from exc

    guarded = [Depends(require_token)]

    @app.get("/health", dependencies=guarded)
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/gpu", dependencies=guarded)
    def gpu_info() -> dict[str, Any]:
        return gpu_probe()

    @app.get("/engine", dependencies=guarded)
    def engine_status() -> dict[str, Any]:
        return engine.status()

    @app.post("/engine:start", dependencies=guarded)
    def engine_start() -> dict[str, Any]:
        return run(engine.start)

    @app.post("/engine:stop", dependencies=guarded)
    def engine_stop() -> dict[str, Any]:
        return run(engine.stop)

    @app.post("/engine:restart", dependencies=guarded)
    def engine_restart() -> dict[str, Any]:
        return run(engine.restart)

    @app.post("/training-runs", dependencies=guarded)
    def training_start(spec: RunSpec) -> dict[str, Any]:
        """A validated run spec only: the agent builds the kohya command itself."""
        return run(lambda: training.start(spec))

    @app.get("/training-runs/{run_id}", dependencies=guarded)
    def training_status(run_id: str) -> dict[str, Any]:
        return run(lambda: training.status(run_id))

    @app.post("/training-runs/{run_id}:cancel", dependencies=guarded)
    def training_cancel(run_id: str) -> dict[str, Any]:
        return run(lambda: training.cancel(run_id))

    return app


def main() -> None:
    import uvicorn

    cfg = AgentSettings()
    if cfg.host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("The host agent only listens on loopback (ADR-012).")
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
