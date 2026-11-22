"""System endpoints. Full status aggregation arrives in WP-16."""

from fastapi import APIRouter
from pydantic import BaseModel

from asset_studio import __version__

router = APIRouter()


class Health(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=Health)
def health() -> Health:
    """Liveness probe: the API process is up."""
    return Health(status="ok", version=__version__)
