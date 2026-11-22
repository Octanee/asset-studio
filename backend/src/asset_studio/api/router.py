"""Top-level API router."""

from fastapi import APIRouter

from asset_studio.api import assets, audit, projects, session, system

api_router = APIRouter()
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(session.router, prefix="/session", tags=["session"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(assets.assets_router, prefix="/assets", tags=["assets"])
api_router.include_router(assets.versions_router, prefix="/versions", tags=["assets"])
