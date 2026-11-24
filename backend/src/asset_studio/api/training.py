"""LoRA training API (WP-13: FR-070-FR-075, RULE-016, RULE-017). Only the user changes
datasets and starts runs; a run is a ``train`` job on the GPU lane."""

import mimetypes
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from asset_studio.api.idempotency import Idem
from asset_studio.api.references import _IMAGE_BODY, _read_body
from asset_studio.api.schemas import JobOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.errors import DomainError
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.providers.engine import EngineMonitor, get_engine_monitor
from asset_studio.modules.storage.local import LocalStorage, get_storage
from asset_studio.modules.training import service
from asset_studio.modules.training.service import Family

project_router = APIRouter()
datasets_router = APIRouter()
items_router = APIRouter()
runs_router = APIRouter()
Db = Annotated[Session, Depends(get_session)]
Files = Annotated[LocalStorage, Depends(get_storage)]
Engine = Annotated[EngineMonitor, Depends(get_engine_monitor)]


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    trigger_word: str
    archived_at: datetime | None
    created_at: datetime
    images: int = 0


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    trigger_word: str = Field(min_length=2, max_length=40)


class DatasetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    trigger_word: str | None = Field(default=None, min_length=2, max_length=40)
    archived: bool | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    dataset_id: uuid.UUID
    source: str
    asset_version_id: uuid.UUID | None
    width: int
    height: int
    caption: str
    created_at: datetime


class VersionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class CaptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caption: str = Field(max_length=1000)


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: uuid.UUID
    family: Family
    base_model_id: str = Field(min_length=1, max_length=120)
    steps: int | None = Field(default=None, ge=1, le=20_000)
    network_dim: int = Field(default=16, ge=4, le=128)
    network_alpha: int = Field(default=8, ge=1, le=128)
    learning_rate: float = Field(default=1e-4, gt=0, le=1e-2)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    acknowledged_estimate: bool = False

    def request(self) -> service.RunRequest:
        return service.RunRequest(**self.model_dump(exclude={"acknowledged_estimate"}))


class EstimateOut(BaseModel):
    family: str
    steps: int
    resolution: int
    seconds: int
    seconds_per_step: float
    vram_mb: int | None
    recommended_vram_mb: int
    warning: bool
    images: int
    default_steps: int
    min_steps: int
    max_steps: int


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    dataset_id: uuid.UUID
    family_id: str
    base_model_id: str
    params: dict[str, Any]
    images: int
    estimate: dict[str, Any]
    acknowledged_estimate: bool
    output_name: str
    job_id: uuid.UUID | None
    output_model_id: str | None
    created_by_actor: str
    created_at: datetime
    job: JobOut | None = None


def gpu_vram_mb(engine: EngineMonitor) -> int | None:
    """The GPU's total VRAM, from the host agent (nvidia-smi) or the engine; None if unknown."""
    status = engine.status()
    gpus = ((status.get("agent") or {}).get("gpu") or {}).get("gpus") or []
    for gpu in gpus:
        if gpu.get("memory_total_mb"):
            return int(gpu["memory_total_mb"])
    for device in status.get("devices") or []:
        if device.get("vram_total_mb"):
            return int(device["vram_total_mb"])
    return None


def _run_out(db: Session, run: Any) -> RunOut:
    out = RunOut.model_validate(run)
    if run.job_id:
        out.job = JobOut.model_validate(jobs.get_job(db, run.job_id))
    return out


# --- datasets (FR-070) -------------------------------------------------------------------


@project_router.get("/{project_id}/datasets", response_model=list[DatasetOut])
def list_datasets(
    db: Db, _: CurrentActor, project_id: uuid.UUID, include_archived: bool = False
) -> list[DatasetOut]:
    return [
        DatasetOut.model_validate(d).model_copy(update={"images": n})
        for d, n in service.list_datasets(db, project_id, include_archived)
    ]


@project_router.post("/{project_id}/datasets", response_model=DatasetOut, status_code=201)
def create_dataset(db: Db, actor: CurrentActor, project_id: uuid.UUID, body: DatasetCreate) -> Any:
    return service.create_dataset(db, project_id, body.name, body.trigger_word, actor)


@datasets_router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(db: Db, _: CurrentActor, dataset_id: uuid.UUID) -> DatasetOut:
    dataset = service.get_dataset(db, dataset_id)
    count = len(service.list_items(db, dataset_id))
    return DatasetOut.model_validate(dataset).model_copy(update={"images": count})


@datasets_router.patch("/{dataset_id}", response_model=DatasetOut)
def update_dataset(
    db: Db, actor: CurrentActor, dataset_id: uuid.UUID, body: DatasetUpdate
) -> DatasetOut:
    service.update_dataset(db, dataset_id, actor, **body.model_dump(exclude_none=True))
    return get_dataset(db, actor, dataset_id)


@datasets_router.get("/{dataset_id}/items", response_model=list[ItemOut])
def list_items(db: Db, _: CurrentActor, dataset_id: uuid.UUID) -> list[Any]:
    return service.list_items(db, dataset_id)


@datasets_router.post("/{dataset_id}/items:versions", response_model=list[ItemOut], status_code=201)
def add_versions(db: Db, actor: CurrentActor, dataset_id: uuid.UUID, body: VersionsIn) -> list[Any]:
    """Approved (or published) versions of the project (RULE-017)."""
    return service.add_versions(db, dataset_id, body.version_ids, actor)


@datasets_router.post(
    "/{dataset_id}/items", response_model=ItemOut, status_code=201, openapi_extra=_IMAGE_BODY
)
async def upload_item(
    request: Request,
    db: Db,
    files: Files,
    actor: CurrentActor,
    dataset_id: uuid.UUID,
    caption: Annotated[str, Query(max_length=1000)] = "",
) -> Any:
    data = await _read_body(request)
    return await run_in_threadpool(
        service.upload, db, files, dataset_id, data, caption=caption, actor=actor
    )


# --- items (FR-071) ------------------------------------------------------------------------


@items_router.patch("/{item_id}", response_model=ItemOut)
def set_caption(db: Db, actor: CurrentActor, item_id: uuid.UUID, body: CaptionIn) -> Any:
    return service.set_caption(db, item_id, body.caption, actor)


@items_router.delete("/{item_id}", status_code=204)
def remove_item(db: Db, files: Files, actor: CurrentActor, item_id: uuid.UUID) -> Response:
    service.remove_item(db, files, item_id, actor)
    return Response(status_code=204)


@items_router.get("/{item_id}/file")
def item_file(db: Db, files: Files, _: CurrentActor, item_id: uuid.UUID) -> FileResponse:
    item = service.get_item(db, item_id)
    try:
        path = files.path(item.storage_key)
    except FileNotFoundError as exc:
        raise DomainError(404, "FILE_NOT_AVAILABLE", "The image file is missing.") from exc
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


# --- runs (FR-072-FR-075, RULE-016) --------------------------------------------------------


@runs_router.post(":estimate", response_model=EstimateOut)
def estimate(db: Db, _: CurrentActor, engine: Engine, body: RunIn) -> dict[str, Any]:
    """The run's time on this GPU and whether it needs the RULE-016 acknowledgement."""
    vram = gpu_vram_mb(engine)
    _dataset, _model, images, est = service.plan(db, body.request(), vram)
    p = service.PRESETS[body.family]
    return est | {
        "images": images,
        "default_steps": service.default_steps(body.family, images),
        "min_steps": p.min_steps,
        "max_steps": p.max_steps,
    }


@runs_router.post("", response_model=RunOut, status_code=202)
def start_run(db: Db, actor: CurrentActor, engine: Engine, idem: Idem, body: RunIn) -> Any:
    def work() -> RunOut:
        run = service.start_run(
            db,
            body.request(),
            vram_mb=gpu_vram_mb(engine),
            acknowledged_estimate=body.acknowledged_estimate,
            actor=actor,
        )
        return _run_out(db, run)

    return idem.run(RunOut, 202, body.model_dump(mode="json"), work)


@runs_router.get("", response_model=list[RunOut])
def list_runs(db: Db, _: CurrentActor, project_id: uuid.UUID) -> list[RunOut]:
    return [_run_out(db, r) for r in service.list_runs(db, project_id)]


@runs_router.get("/{run_id}", response_model=RunOut)
def get_run(db: Db, _: CurrentActor, run_id: uuid.UUID) -> RunOut:
    return _run_out(db, service.get_run(db, run_id))
