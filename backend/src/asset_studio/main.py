"""FastAPI application factory."""

from fastapi import FastAPI

from asset_studio import __version__
from asset_studio.api import problems
from asset_studio.api.router import api_router
from asset_studio.api.security import HostOriginMiddleware
from asset_studio.config import get_settings
from asset_studio.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(title="Universal Asset Studio API", version=__version__)
    app.add_middleware(HostOriginMiddleware)
    problems.install(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
