"""Top-level API router."""

from fastapi import APIRouter

from asset_studio.api import system

api_router = APIRouter()
api_router.include_router(system.router, prefix="/system", tags=["system"])
