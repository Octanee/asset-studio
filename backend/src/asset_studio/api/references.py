"""References API (FR-025, FR-026).

Uploads send the image itself as the request body (``Content-Type: image/png``, ...), with
the role and the original file name in the query. The server checks the bytes, not the
declared type, so no multipart parser is needed.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.errors import DomainError
from asset_studio.modules.references import service
from asset_studio.modules.storage.local import LocalStorage, get_storage

project_router = APIRouter()
router = APIRouter()
Db = Annotated[Session, Depends(get_session)]
Files = Annotated[LocalStorage, Depends(get_storage)]
Role = Literal[
    "style",
    "character",
    "pose",
    "composition",
    "colour",
    "anatomy",
    "equipment",
    "background",
    "other",
]
LinkTarget = Literal["style", "character"]


class ReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    role: str
    name: str
    sha256: str
    mime: str
    width: int
    height: int
    bytes: int
    archived_at: datetime | None
    created_at: datetime


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    reference_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    weight: float
    created_at: datetime


class ReferenceUpdate(BaseModel):
    role: Role | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)


class LinkRequest(BaseModel):
    weight: float = Field(default=1.0, ge=0, le=2)


_IMAGE_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            mime: {"schema": {"type": "string", "format": "binary"}}
            for mime in ("image/png", "image/jpeg", "image/webp")
        },
    }
}


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > service.MAX_BYTES:
        raise DomainError(413, "FILE_TOO_LARGE", "The file is larger than 30 MB.")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > service.MAX_BYTES:
            raise DomainError(413, "FILE_TOO_LARGE", "The file is larger than 30 MB.")
        chunks.append(chunk)
    if size == 0:
        raise DomainError(422, "FILE_EMPTY", "The request has no file.")
    return b"".join(chunks)


@project_router.get("/{project_id}/references", response_model=list[ReferenceOut])
def list_references(
    db: Db,
    _: CurrentActor,
    project_id: uuid.UUID,
    role: Role | None = None,
    target_type: LinkTarget | None = None,
    target_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> list[Any]:
    return service.list_references(
        db,
        project_id,
        role=role,
        target_type=target_type,
        target_id=target_id,
        include_archived=include_archived,
    )


@project_router.post(
    "/{project_id}/references",
    response_model=ReferenceOut,
    status_code=201,
    openapi_extra=_IMAGE_BODY,
)
async def upload_reference(
    request: Request,
    db: Db,
    files: Files,
    actor: CurrentActor,
    project_id: uuid.UUID,
    role: Role,
    name: Annotated[str, Query(max_length=255)] = "reference",
) -> Any:
    data = await _read_body(request)
    # The service is synchronous (database and disk); keep it off the event loop.
    return await run_in_threadpool(
        service.upload, db, files, project_id, data, role=role, name=name, actor=actor
    )


@router.get("/{reference_id}", response_model=ReferenceOut)
def get_reference(db: Db, _: CurrentActor, reference_id: uuid.UUID) -> Any:
    return service.get_reference(db, reference_id)


@router.patch("/{reference_id}", response_model=ReferenceOut)
def update_reference(
    db: Db, actor: CurrentActor, reference_id: uuid.UUID, body: ReferenceUpdate
) -> Any:
    return service.update(db, reference_id, actor, role=body.role, name=body.name)


@router.post("/{reference_id}/archive", response_model=ReferenceOut)
def archive_reference(db: Db, actor: CurrentActor, reference_id: uuid.UUID) -> Any:
    return service.set_archived(db, reference_id, True, actor)


@router.post("/{reference_id}/restore", response_model=ReferenceOut)
def restore_reference(db: Db, actor: CurrentActor, reference_id: uuid.UUID) -> Any:
    return service.set_archived(db, reference_id, False, actor)


@router.get("/{reference_id}/file")
def reference_file(db: Db, files: Files, _: CurrentActor, reference_id: uuid.UUID) -> FileResponse:
    f = service.reference_file(db, files, reference_id)
    return FileResponse(
        f.path,
        media_type=f.mime,
        filename=f.filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.get("/{reference_id}/links", response_model=list[LinkOut])
def list_links(db: Db, _: CurrentActor, reference_id: uuid.UUID) -> list[Any]:
    return service.links_of(db, reference_id)


@router.put("/{reference_id}/links/{target_type}/{target_id}", response_model=LinkOut)
def link_reference(
    db: Db,
    actor: CurrentActor,
    reference_id: uuid.UUID,
    target_type: LinkTarget,
    target_id: uuid.UUID,
    body: LinkRequest,
) -> Any:
    return service.link(db, reference_id, target_type, target_id, actor, weight=body.weight)


@router.delete("/{reference_id}/links/{target_type}/{target_id}", status_code=204)
def unlink_reference(
    db: Db,
    actor: CurrentActor,
    reference_id: uuid.UUID,
    target_type: LinkTarget,
    target_id: uuid.UUID,
) -> None:
    service.unlink(db, reference_id, target_type, target_id, actor)
