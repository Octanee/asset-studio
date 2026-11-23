"""Assets, versions and lifecycle API (FR-049 to FR-055, FR-057, FR-059, FR-061 to FR-064)."""

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
    CommentOut,
    DuplicateOut,
    JobOut,
    QueueVersionOut,
    RuleResultOut,
    TagOut,
    TransitionOut,
    ValidationOut,
    VersionDetail,
    VersionOut,
)
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.assets import collections, service
from asset_studio.modules.assets.lifecycle import ClientAction, StateName
from asset_studio.modules.processing import service as processing
from asset_studio.modules.quality import service as quality
from asset_studio.modules.review import service as review
from asset_studio.modules.review.models import MAX_COMMENT
from asset_studio.modules.storage.local import LocalStorage, get_storage

assets_router = APIRouter()
versions_router = APIRouter()
Db = Annotated[Session, Depends(get_session)]
Files = Annotated[LocalStorage, Depends(get_storage)]


class TransitionRequest(BaseModel):
    action: ClientAction
    reason: str = Field(default="", max_length=1000)


class AssetPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    tags: list[Annotated[str, Field(max_length=100)]] | None = Field(default=None, max_length=50)
    favorite: bool | None = None


class CommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_COMMENT)


Sort = Literal["newest", "oldest", "name", "updated"]


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
    style_id: uuid.UUID | None = None,
    character_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
    tag: Annotated[str | None, Query(max_length=40)] = None,
    favorite: bool | None = None,
    include_archived: bool = False,
    sort: Sort = "newest",
    before: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AssetSummary]:
    """Search and filter the library (FR-050). ``before`` pages the newest-first sort;
    the other sorts page with ``offset``."""
    rows = service.list_assets(
        db,
        project_id=project_id,
        category=category,
        state=state,
        q=q,
        style_id=style_id,
        character_id=character_id,
        collection_id=collection_id,
        tag=tag,
        favorite=favorite,
        include_archived=include_archived,
        sort=sort,
        before=before,
        offset=offset,
        limit=limit,
    )
    member = collections.collections_of(db, [r.asset.id for r in rows])
    return [
        AssetSummary(
            **AssetOut.model_validate(r.asset).model_dump(),
            latest_version=VersionOut.model_validate(r.latest) if r.latest else None,
            version_count=r.version_count,
            collection_ids=member[r.asset.id],
        )
        for r in rows
    ]


@assets_router.get("/tags", response_model=list[TagOut])
def list_tags(
    db: Db,
    _: CurrentActor,
    project_id: uuid.UUID,
    prefix: Annotated[str, Query(max_length=40)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[TagOut]:
    """The project's tags for auto-suggest, most used first (FR-049)."""
    return [
        TagOut(tag=t, count=n) for t, n in service.tag_suggestions(db, project_id, prefix, limit)
    ]


def _asset_detail(db: Session, asset_id: uuid.UUID) -> AssetDetail:
    asset = service.get_asset(db, asset_id)
    return AssetDetail(
        **AssetOut.model_validate(asset).model_dump(),
        versions=[VersionOut.model_validate(v) for v in service.list_versions(db, asset_id)],
        collection_ids=collections.collections_of(db, [asset.id])[asset.id],
    )


@assets_router.get("/{asset_id}", response_model=AssetDetail)
def get_asset(db: Db, _: CurrentActor, asset_id: uuid.UUID) -> AssetDetail:
    return _asset_detail(db, asset_id)


@assets_router.patch("/{asset_id}", response_model=AssetDetail)
def update_asset(db: Db, actor: CurrentActor, asset_id: uuid.UUID, body: AssetPatch) -> AssetDetail:
    """Rename, tag (FR-049) or mark as favourite (FR-057); user only."""
    service.update_asset(
        db, asset_id, actor, name=body.name, tags=body.tags, favorite=body.favorite
    )
    return _asset_detail(db, asset_id)


@assets_router.get("/{asset_id}/versions", response_model=list[VersionOut])
def list_versions(db: Db, _: CurrentActor, asset_id: uuid.UUID) -> list[Any]:
    return service.list_versions(db, asset_id)


@assets_router.post("/{asset_id}/archive", response_model=AssetOut)
def archive_asset(db: Db, actor: CurrentActor, asset_id: uuid.UUID) -> Any:
    return service.set_asset_archived(db, asset_id, True, actor)


@assets_router.post("/{asset_id}/restore", response_model=AssetOut)
def restore_asset(db: Db, actor: CurrentActor, asset_id: uuid.UUID) -> Any:
    return service.set_asset_archived(db, asset_id, False, actor)


@versions_router.get("", response_model=list[QueueVersionOut])
def list_versions_across(
    db: Db,
    _: CurrentActor,
    project_id: uuid.UUID | None = None,
    state: StateName | None = None,
    after: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[QueueVersionOut]:
    """Versions across assets, oldest first; ``state=awaiting_review`` is the review queue
    (FR-061). ``after`` is a cursor (a version id)."""
    return [
        QueueVersionOut(
            **VersionOut.model_validate(v).model_dump(), asset=AssetOut.model_validate(a)
        )
        for v, a in service.list_versions_by_state(
            db, project_id=project_id, state=state, after=after, limit=limit
        )
    ]


@versions_router.get("/{version_id}", response_model=VersionDetail)
def get_version(db: Db, _: CurrentActor, version_id: uuid.UUID) -> VersionDetail:
    return _version_detail(db, version_id)


@versions_router.post("/{version_id}/transitions", response_model=VersionDetail)
def run_transition(
    db: Db, actor: CurrentActor, version_id: uuid.UUID, body: TransitionRequest
) -> VersionDetail:
    if body.action == "retry_processing":  # T-04R starts the pipeline again
        processing.start(db, version_id, actor)
    else:
        service.transition(db, version_id, body.action, actor, reason=body.reason)
    return _version_detail(db, version_id)


@versions_router.post("/{version_id}:process", response_model=JobOut, status_code=202)
def process_version(db: Db, actor: CurrentActor, version_id: uuid.UUID) -> Any:
    """Process a ``generated`` version (T-02) or retry a failed one (T-04R) (FR-065)."""
    return processing.start(db, version_id, actor)


def _validation(report: quality.Report) -> ValidationOut:
    return ValidationOut(
        run_id=report.run_id,
        checked_at=report.results[0].created_at if report.results else None,
        summary=report.summary,
        results=[RuleResultOut.model_validate(r) for r in report.results],
    )


@versions_router.get("/{version_id}/validation", response_model=ValidationOut)
def get_validation(db: Db, _: CurrentActor, version_id: uuid.UUID) -> ValidationOut:
    service.get_version(db, version_id)
    return _validation(quality.latest(db, version_id))


@versions_router.post("/{version_id}:validate", response_model=ValidationOut)
def validate_version(
    db: Db, files: Files, actor: CurrentActor, version_id: uuid.UUID
) -> ValidationOut:
    """Validate again, e.g. after the project's rules changed (FR-060)."""
    return _validation(quality.run(db, files, service.get_version(db, version_id), actor))


@versions_router.get("/{version_id}/comments", response_model=list[CommentOut])
def list_comments(db: Db, _: CurrentActor, version_id: uuid.UUID) -> list[Any]:
    return review.list_comments(db, version_id)


@versions_router.post("/{version_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(db: Db, actor: CurrentActor, version_id: uuid.UUID, body: CommentRequest) -> Any:
    """Comment on a version (FR-061). Claude may always comment over MCP (FR-064)."""
    return review.add_comment(db, version_id, body.body, actor)


@versions_router.get("/{version_id}/duplicates", response_model=list[DuplicateOut])
def list_duplicates(db: Db, _: CurrentActor, version_id: uuid.UUID) -> list[DuplicateOut]:
    """Other versions of the project with the same file or a near-identical image (FR-059)."""
    return [
        DuplicateOut(
            version=VersionOut.model_validate(d.version),
            asset=AssetOut.model_validate(d.asset),
            distance=d.distance,
            exact=d.exact,
        )
        for d in review.duplicates(db, version_id)
    ]


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
    size: Literal["original", "processed", "thumb", "preview"] = "original",
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
