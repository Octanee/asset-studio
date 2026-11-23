"""Top-level API router."""

from fastapi import APIRouter

from asset_studio.api import (
    assets,
    audit,
    jobs,
    poses,
    projects,
    references,
    session,
    styles,
    system,
)

api_router = APIRouter()
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(session.router, prefix="/session", tags=["session"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(styles.project_router, prefix="/projects", tags=["styles"])
api_router.include_router(styles.styles_router, prefix="/styles", tags=["styles"])
api_router.include_router(styles.characters_router, prefix="/characters", tags=["styles"])
api_router.include_router(references.project_router, prefix="/projects", tags=["references"])
api_router.include_router(references.router, prefix="/references", tags=["references"])
api_router.include_router(poses.project_router, prefix="/projects", tags=["poses"])
api_router.include_router(poses.router, prefix="/poses", tags=["poses"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(assets.assets_router, prefix="/assets", tags=["assets"])
api_router.include_router(assets.versions_router, prefix="/versions", tags=["assets"])
api_router.include_router(jobs.jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(jobs.events_router, prefix="/events", tags=["events"])
