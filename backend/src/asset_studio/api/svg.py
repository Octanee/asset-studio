"""SVG API (FR-045-FR-047, UC-014): templates, a live preview and queueing a version."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from asset_studio.api.idempotency import Idem
from asset_studio.api.schemas import JobOut
from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.modules.svg import service
from asset_studio.modules.svg.service import SvgSpec
from asset_studio.modules.svg.templates import TEMPLATES

router = APIRouter()
Db = Annotated[Session, Depends(get_session)]


class ParamOut(BaseModel):
    name: str
    kind: Literal["glyph", "color", "number"]
    default: str | float
    min: float | None
    max: float | None
    step: float | None
    options: list[str]


class TemplateOut(BaseModel):
    id: str
    version: int
    name: str
    description: str
    params: list[ParamOut]


class SvgProblem(BaseModel):
    code: str
    param: str
    detail: str


class SvgReport(BaseModel):
    removed_elements: int
    removed_attributes: int
    bytes_in: int
    bytes_out: int


class TemplateRef(BaseModel):
    id: str
    version: int


class SvgPreviewOut(BaseModel):
    ready: bool
    problems: list[SvgProblem]
    template: TemplateRef
    params: dict[str, Any]
    params_hash: str
    # Cleaned and optimised: exactly the file a queued job stores.
    svg: str
    sha256: str
    width: float
    height: float
    report: SvgReport
    palette: list[str]


class SvgQueuedOut(BaseModel):
    asset_id: uuid.UUID
    job: JobOut


@router.get("/templates", response_model=list[TemplateOut])
def templates(_: CurrentActor) -> list[TemplateOut]:
    return [
        TemplateOut(
            id=t.id,
            version=t.version,
            name=t.name,
            description=t.description,
            params=[
                ParamOut(
                    name=p.name,
                    kind=p.kind,
                    default=p.default,
                    min=p.min,
                    max=p.max,
                    step=p.step,
                    options=list(p.options),
                )
                for p in t.params
            ],
        )
        for t in TEMPLATES.values()
    ]


@router.post(":preview", response_model=SvgPreviewOut)
def preview(db: Db, _: CurrentActor, spec: SvgSpec) -> SvgPreviewOut:
    r = service.render(db, spec)
    return SvgPreviewOut(
        ready=not r.problems,
        problems=[SvgProblem(**p) for p in r.problems],
        template=TemplateRef(id=r.template.id, version=r.template.version),
        params=r.params,
        params_hash=r.params_hash,
        svg=r.clean.svg,
        sha256=r.sha256,
        width=r.clean.width,
        height=r.clean.height,
        report=SvgReport(**r.clean.report),
        palette=r.style["palette"] if r.style else [],
    )


@router.post("", response_model=SvgQueuedOut, status_code=202)
def create(db: Db, actor: CurrentActor, idem: Idem, spec: SvgSpec) -> Any:
    def work() -> SvgQueuedOut:
        q = service.queue(db, spec, actor)
        return SvgQueuedOut(asset_id=q.asset_id, job=JobOut.model_validate(q.job))

    return idem.run(SvgQueuedOut, 202, spec, work)
