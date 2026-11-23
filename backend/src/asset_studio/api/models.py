"""Models API (FR-080-FR-084, RULE-007, RULE-008)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from asset_studio.api.schemas import JobOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.models import service
from asset_studio.modules.models.models import Licence, Model

router = APIRouter()
project_router = APIRouter()
Db = Annotated[Session, Depends(get_session)]
Kind = Literal["checkpoint", "lora", "controlnet", "ip_adapter", "clip_vision", "vae", "pose"]
ModelId = Annotated[str, Field(min_length=1, max_length=120)]


class LicenceOut(BaseModel):
    id: str
    name: str
    commercial_use: str
    url: str
    notes: str


class ModelOut(BaseModel):
    id: str
    name: str
    kind: str
    family_id: str | None
    licence: LicenceOut
    file_name: str
    source_url: str | None
    sha256: str | None
    bytes: int | None
    # Weights size: a lower bound for the VRAM the model needs (FR-080).
    vram_mb: int | None
    origin: str
    notes: str
    status: str
    file_bytes: int | None
    verification: str
    verified_at: datetime | None
    # With ?project_id: does the licence conflict with the project's intended use (RULE-007)?
    licence_conflict: bool | None = None
    licence_acknowledged: bool | None = None


class ScanOut(BaseModel):
    installed: int
    added: list[str]
    missing: list[str]


class CheckRequest(BaseModel):
    model_ids: list[ModelId] = Field(min_length=1, max_length=20)
    project_id: uuid.UUID | None = None


class Problem(BaseModel):
    code: str
    model_id: str | None
    detail: str


class CheckOut(BaseModel):
    compatible: bool
    problems: list[Problem]
    # Models whose licence still needs the user's confirmation for this project.
    licence_confirmation_required: list[str]


class DownloadConfirm(BaseModel):
    """The user's approval of exactly what is fetched (RULE-008)."""

    file_name: str
    source_url: str
    bytes: int


class FamilyUpdate(BaseModel):
    family_id: str | None


class AckRequest(BaseModel):
    model_id: ModelId
    note: str = Field(default="", max_length=500)


class AckOut(BaseModel):
    project_id: uuid.UUID
    model_id: str
    licence_id: str
    intended_use: str
    actor: str
    note: str
    at: datetime


def _out(db: Session, models: list[Model], project_id: uuid.UUID | None) -> list[ModelOut]:
    status = service.licence_status(db, project_id, models) if project_id else {}
    out = []
    for m in models:
        lic = db.get(Licence, m.licence_id)
        assert lic is not None  # noqa: S101 - foreign key
        s = status.get(m.id)
        out.append(
            ModelOut(
                id=m.id,
                name=m.name,
                kind=m.kind,
                family_id=m.family_id,
                licence=LicenceOut(
                    id=lic.id,
                    name=lic.name,
                    commercial_use=lic.commercial_use,
                    url=lic.url,
                    notes=lic.notes,
                ),
                file_name=m.file_name,
                source_url=m.source_url,
                sha256=m.sha256,
                bytes=m.bytes,
                vram_mb=-(-(m.bytes or m.file_bytes or 0) // (1024 * 1024)) or None,
                origin=m.origin,
                notes=m.notes,
                status=m.status,
                file_bytes=m.file_bytes,
                verification=m.verification,
                verified_at=m.verified_at,
                licence_conflict=s.conflict if s else None,
                licence_acknowledged=s.acknowledged if s else None,
            )
        )
    return out


@router.get("", response_model=list[ModelOut])
def list_models(
    db: Db, _: CurrentActor, kind: Kind | None = None, project_id: uuid.UUID | None = None
) -> list[ModelOut]:
    service.sync_catalogue(db)
    return _out(db, service.list_models(db, kind), project_id)


@router.post(":rescan", response_model=ScanOut)
def rescan(db: Db, actor: CurrentActor) -> Any:
    return service.scan(db, actor)


@router.post(":check", response_model=CheckOut)
def check(db: Db, _: CurrentActor, body: CheckRequest) -> CheckOut:
    problems = service.compatibility(db, body.model_ids)
    pending: list[str] = []
    if body.project_id is not None:
        models = [service.get_model(db, mid) for mid in dict.fromkeys(body.model_ids)]
        status = service.licence_status(db, body.project_id, models)
        pending = [m.id for m in models if status[m.id].conflict and not status[m.id].acknowledged]
    return CheckOut(
        compatible=not problems,
        problems=[Problem(**p) for p in problems],
        licence_confirmation_required=pending,
    )


@router.get("/{model_id}", response_model=ModelOut)
def get_model(
    db: Db, _: CurrentActor, model_id: str, project_id: uuid.UUID | None = None
) -> ModelOut:
    service.sync_catalogue(db)
    service.reconcile(db)
    return _out(db, [service.get_model(db, model_id)], project_id)[0]


@router.patch("/{model_id}", response_model=ModelOut)
def update_model(db: Db, actor: CurrentActor, model_id: str, body: FamilyUpdate) -> ModelOut:
    return _out(db, [service.set_family(db, model_id, body.family_id, actor)], None)[0]


@router.post("/{model_id}:download", response_model=JobOut, status_code=202)
def download(db: Db, actor: CurrentActor, model_id: str, body: DownloadConfirm) -> Any:
    return service.request_download(
        db,
        model_id,
        actor,
        file_name=body.file_name,
        source_url=body.source_url,
        bytes_=body.bytes,
    )


@router.post("/{model_id}:verify", response_model=JobOut, status_code=202)
def verify(db: Db, actor: CurrentActor, model_id: str) -> Any:
    return service.request_verify(db, model_id, actor)


@project_router.post(
    "/{project_id}/licence-acknowledgements", response_model=AckOut, status_code=201
)
def acknowledge(db: Db, actor: CurrentActor, project_id: uuid.UUID, body: AckRequest) -> Any:
    return service.acknowledge(db, project_id, body.model_id, actor, body.note)
