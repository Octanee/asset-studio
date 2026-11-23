"""Top-level API router."""

from fastapi import APIRouter

from asset_studio.api import (
    assets,
    audit,
    collections,
    generation,
    jobs,
    models,
    poses,
    projects,
    publishing,
    references,
    session,
    styles,
    system,
    workflows,
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
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(generation.router, prefix="/generations", tags=["generation"])
api_router.include_router(generation.versions_router, prefix="/versions", tags=["generation"])
api_router.include_router(models.project_router, prefix="/projects", tags=["models"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(assets.assets_router, prefix="/assets", tags=["assets"])
api_router.include_router(assets.versions_router, prefix="/versions", tags=["assets"])
api_router.include_router(collections.project_router, prefix="/projects", tags=["collections"])
api_router.include_router(collections.router, prefix="/collections", tags=["collections"])
api_router.include_router(publishing.roots_router, prefix="/export-roots", tags=["publishing"])
api_router.include_router(publishing.project_router, prefix="/projects", tags=["publishing"])
api_router.include_router(publishing.presets_router, prefix="/presets", tags=["publishing"])
api_router.include_router(publishing.targets_router, prefix="/targets", tags=["publishing"])
api_router.include_router(publishing.router, prefix="/publications", tags=["publishing"])
api_router.include_router(jobs.jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(jobs.events_router, prefix="/events", tags=["events"])
