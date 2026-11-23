"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from asset_studio import __version__
from asset_studio.api import problems
from asset_studio.api.router import api_router
from asset_studio.api.security import HostOriginMiddleware
from asset_studio.config import get_settings
from asset_studio.logging import configure_logging
from asset_studio.models import load_all
from asset_studio.modules.storage.local import get_storage


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_storage().clean_staging()  # temp files from an interrupted write
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    load_all()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(title="Universal Asset Studio API", version=__version__, lifespan=lifespan)
    app.add_middleware(HostOriginMiddleware)
    problems.install(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
