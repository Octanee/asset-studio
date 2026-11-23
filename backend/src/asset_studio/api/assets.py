"""Assets, versions and lifecycle API (FR-050, FR-051, FR-053 to FR-055, FR-061 to FR-064)."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from asset_studio.api.schemas import (
    AssetDetail,
    AssetOut,
    AssetSummary,
    TransitionOut,
    VersionDetail,
    VersionOut,
)
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.assets import service
from asset_studio.modules.assets.lifecycle import ClientAction, StateName
from asset_studio.modules.storage.local import LocalStorage, get_storage

assets_router = APIRouter()
versions_router = APIRouter()
Db = Annotated[Session, Depends(get_session)]
Files = Annotated[LocalStorage, Depends(get_storage)]


class TransitionRequest(BaseModel):
    action: ClientAction
    reason: str = Field(default="", max_length=1000)


def _version_detail(db: Session, version_id: uuid.UUID) -> VersionDetail:
    version = service.get_version(db, version_id)
    return VersionDetail(
        **VersionOut.model_validate(version).model_dump(),
        history=[TransitionOut.model_validate(t) for t in service.history(db, version_id)],
    )


@assets_router.get("", response_model=list[AssetSummary])
def list_assets(
    db: Db,
    _: CurrentActor,
    project_id: uuid.UUID | None = None,
    category: str | None = None,
    state: StateName | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    include_archived: bool = False,
    before: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AssetSummary]:
    rows = service.list_assets(
        db,
        project_id=project_id,
        category=category,
        state=state,
        q=q,
        include_archived=include_archived,
        before=before,
        limit=limit,
    )
    return [
        AssetSummary(
            **AssetOut.model_validate(r.asset).model_dump(),
            latest_version=VersionOut.model_validate(r.latest) if r.latest else None,
            version_count=r.version_count,
        )
        for r in rows
    ]


@assets_router.get("/{asset_id}", response_model=AssetDetail)
def get_asset(db: Db, _: CurrentActor, asset_id: uuid.UUID) -> AssetDetail:
    asset = service.get_asset(db, asset_id)
    return AssetDetail(
        **AssetOut.model_validate(asset).model_dump(),
        versions=[VersionOut.model_validate(v) for v in service.list_versions(db, asset_id)],
    )


@assets_router.get("/{asset_id}/versions", response_model=list[VersionOut])
def list_versions(db: Db, _: CurrentActor, asset_id: uuid.UUID) -> list[Any]:
    return service.list_versions(db, asset_id)


@assets_router.post("/{asset_id}/archive", response_model=AssetOut)
def archive_asset(db: Db, actor: CurrentActor, asset_id: uuid.UUID) -> Any:
    return service.set_asset_archived(db, asset_id, True, actor)


@assets_router.post("/{asset_id}/restore", response_model=AssetOut)
def restore_asset(db: Db, actor: CurrentActor, asset_id: uuid.UUID) -> Any:
    return service.set_asset_archived(db, asset_id, False, actor)


@versions_router.get("/{version_id}", response_model=VersionDetail)
def get_version(db: Db, _: CurrentActor, version_id: uuid.UUID) -> VersionDetail:
    return _version_detail(db, version_id)


@versions_router.post("/{version_id}/transitions", response_model=VersionDetail)
def run_transition(
    db: Db, actor: CurrentActor, version_id: uuid.UUID, body: TransitionRequest
) -> VersionDetail:
    service.transition(db, version_id, body.action, actor, reason=body.reason)
    return _version_detail(db, version_id)


@versions_router.delete("/{version_id}", response_model=VersionDetail)
def delete_version(
    db: Db,
    files: Files,
    actor: CurrentActor,
    version_id: uuid.UUID,
    confirm: Annotated[str, Query(description="The version id, typed to confirm.")] = "",
) -> VersionDetail:
    service.delete_version(db, files, version_id, actor, confirm=confirm)
    return _version_detail(db, version_id)


@versions_router.get("/{version_id}/file")
def download_file(
    db: Db,
    files: Files,
    _: CurrentActor,
    version_id: uuid.UUID,
    size: Literal["original", "thumb", "preview"] = "original",
    download: bool = False,
) -> FileResponse:
    f = service.version_file(db, files, version_id, size)
    return FileResponse(
        f.path,
        media_type=f.mime,
        filename=f.filename,
        content_disposition_type="attachment" if download else "inline",
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            # SVG can carry scripts; never let one run in the API origin.
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        },
    )
