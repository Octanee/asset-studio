"""Post-processing pipeline (FR-065, Asset-Lifecycle T-02 to T-04).

After generation each version goes ``generated`` → ``processing`` (T-02) and runs the
project's steps as jobs:

1. ``remove_background`` (GPU lane, optional): BiRefNet through the engine (ADR-010). It
   waits in the queue while the engine is down (RULE-013); everything else keeps working.
2. ``process`` (CPU lane): background fill, resize, convert, optimise, thumbnail and preview,
   then technical validation (FR-060). Success → ``awaiting_review`` (T-03).

A failed or cancelled step → ``processing_failed`` (T-04) with the error; retrying (T-04R)
starts the pipeline again. The original file is never changed (RULE-003): processing adds
its own files next to it, each written once; leftovers of a failed attempt are removed
before the next attempt writes them again.
"""

import functools
import io
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from asset_studio.db import utcnow
from asset_studio.errors import DomainError
from asset_studio.modules.assets import service as assets
from asset_studio.modules.assets.models import AssetVersion
from asset_studio.modules.audit.service import Actor
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.jobs.models import Job
from asset_studio.modules.jobs.runner import Handler, JobCancelled, JobContext, WorkerStopping
from asset_studio.modules.models import service as registry
from asset_studio.modules.models.models import Model
from asset_studio.modules.processing import imaging
from asset_studio.modules.projects.config_schema import ProjectConfig
from asset_studio.modules.projects.service import current_config, get_project
from asset_studio.modules.providers.base import GenerationRequest
from asset_studio.modules.providers.engine import get_engine_monitor, run_generation
from asset_studio.modules.quality import service as quality
from asset_studio.modules.storage.local import LocalStorage, get_storage
from asset_studio.modules.workflows.builtin import remove_background

PREFERRED_SEGMENTATION = ("birefnet-comfy",)
THUMB, PREVIEW = 256, 1024
SOURCE_FORMATS = {"png": "png", "webp": "webp", "jpg": "jpeg"}


def _config(session: Session, version: AssetVersion) -> tuple[uuid.UUID, ProjectConfig]:
    asset = assets.get_asset(session, version.asset_id)
    return asset.project_id, current_config(session, get_project(session, asset.project_id))


def _enqueue(session: Session, version: AssetVersion, kind: str, actor: Actor) -> Job:
    project_id, _ = _config(session, version)
    return jobs.enqueue(
        session,
        kind,
        {"version_id": str(version.id), "asset_id": str(version.asset_id)},
        actor=actor,
        project_id=project_id,
    )


def start(session: Session, version_id: uuid.UUID, actor: Actor) -> Job:
    """Start processing a ``generated`` version (T-02) or retry a failed one (T-04R)."""
    if actor not in ("user", "system"):
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Processing is started by the user or a job.")
    version = assets.get_version(session, version_id)
    if version.state == "generated":
        # T-02 is a system transition; the job records who asked for it.
        assets.transition(session, version_id, "start_processing", "system")
    elif version.state == "processing_failed":
        assets.transition(session, version_id, "retry_processing", actor)
    else:
        raise DomainError(
            409,
            "PROCESSING_NOT_ALLOWED",
            f"A version in state {version.state} cannot be processed.",
            {"state": version.state},
        )
    version.processing = {}
    session.flush()
    _, config = _config(session, version)
    first = "remove_background" if config.processing.remove_background else "process"
    return _enqueue(session, version, first, actor)


# --- jobs ---------------------------------------------------------------------------------


def _begin(session: Session, ctx: JobContext) -> AssetVersion:
    """The version this job works on, in state ``processing``. A job retried from the queue
    after a failure first returns the version to processing (T-04R)."""
    version_id = uuid.UUID(ctx.params["version_id"])
    version = assets.get_version(session, version_id)
    if version.state == "processing_failed":
        assets.transition(session, version_id, "retry_processing", "system")
    elif version.state != "processing":
        raise DomainError(
            409,
            "VERSION_NOT_PROCESSING",
            f"The version is {version.state}, not processing.",
            {"state": version.state},
        )
    return version


def _fail(ctx: JobContext, error: dict[str, str]) -> None:
    with ctx.runner.sessions() as s, s.begin():
        version = s.get(AssetVersion, uuid.UUID(ctx.params["version_id"]))
        if version is None or version.state != "processing":
            return
        version.processing = {
            **(version.processing or {}),
            "error": {**error, "job_id": str(ctx.job_id), "step": ctx.kind},
        }
        assets.transition(s, version.id, "processing_failed", "system", data={"error": error})


def _step(handler: Handler) -> Handler:
    """A failed or cancelled step marks the version ``processing_failed`` (T-04)."""

    @functools.wraps(handler)
    def run(ctx: JobContext) -> dict[str, Any] | None:
        try:
            return handler(ctx)
        except WorkerStopping:
            raise  # the job becomes interrupted and resumes later; the version waits
        except JobCancelled:
            _fail(ctx, {"code": "CANCELLED", "message": "The processing job was cancelled."})
            raise
        except Exception as exc:
            code = str(getattr(exc, "code", type(exc).__name__))
            _fail(ctx, {"code": code, "message": str(exc)[:500]})
            raise

    return run


def _write(storage: LocalStorage, key: str, data: bytes) -> dict[str, Any]:
    storage.delete_prefix(key)  # a leftover of a failed attempt; never a committed file
    stored = storage.put(key, io.BytesIO(data))
    return {"key": stored.key, "sha256": stored.sha256, "bytes": stored.bytes}


def _segmentation_model(session: Session) -> Model:
    registry.sync_catalogue(session)
    registry.reconcile(session)
    rows = [
        m
        for m in session.scalars(select(Model).where(Model.kind == "segmentation"))
        if m.status == "installed" and m.verification != "mismatch"
    ]
    order = PREFERRED_SEGMENTATION
    rows.sort(key=lambda m: (order.index(m.id) if m.id in order else len(order), m.origin, m.id))
    if not rows:
        raise DomainError(
            409,
            "PROCESSING_MODEL_MISSING",
            "Background removal needs a segmentation model (BiRefNet). Install it in Models.",
            {"kind": "segmentation"},
        )
    return rows[0]


def _remove_background(ctx: JobContext) -> dict[str, Any]:
    storage = get_storage()
    with ctx.runner.sessions() as s, s.begin():
        version = _begin(s, ctx)
        project_id, _ = _config(s, version)
        model = _segmentation_model(s)
        registry.licence_gate(s, project_id, [model.id])  # RULE-007
        if version.storage_key is None:
            raise DomainError(410, "VERSION_DELETED", "The version file was deleted.")
        key = version.storage_key
        model_id, model_file = model.id, model.file_name
    original = storage.path(key).read_bytes()
    ctx.progress(state="submitting")
    request = GenerationRequest(
        remove_background(),
        {"model": model_file, "prefix": f"asset_studio/{str(ctx.job_id)[:8]}"},
        {"image": original},
    )
    outputs = run_generation(get_engine_monitor().provider, request, ctx)
    if not outputs:
        raise DomainError(502, "GENERATION_EMPTY", "The engine returned no mask.")
    try:
        cut = imaging.cutout(original, outputs[0].data)
    except imaging.ProcessingError as exc:
        raise DomainError(502, "MASK_INVALID", "The engine's mask is not an image.") from exc
    ctx.check()
    with ctx.runner.sessions() as s, s.begin():
        version = _begin(s, ctx)
        stored = _write(storage, f"{key.rsplit('/', 1)[0]}/cutout.png", cut)
        version.processing = {
            **(version.processing or {}),
            "cutout": {**stored, "model": model_id, "job_id": str(ctx.job_id)},
        }
        job = _enqueue(s, version, "process", "system")
        return {
            "asset_id": str(version.asset_id),
            "versions": [str(version.id)],
            "next_job": str(job.id),
        }


def _process(ctx: JobContext) -> dict[str, Any]:
    storage = get_storage()
    with ctx.runner.sessions() as s, s.begin():
        version = _begin(s, ctx)
        _, config = _config(s, version)
        if version.storage_key is None:
            raise DomainError(410, "VERSION_DELETED", "The version file was deleted.")
        original_key = version.storage_key
        cut = (version.processing or {}).get("cutout")
        if config.processing.remove_background and not cut:
            raise DomainError(
                409, "BACKGROUND_NOT_REMOVED", "Background removal has not run for this version."
            )
        target = imaging.Target(
            width=config.output.width,
            height=config.output.height,
            format=config.output.format,
            background=config.output.background,
            resize=config.processing.resize,
            optimize=config.processing.optimize,
            quality=config.processing.quality,
        )
    source_key = cut["key"] if cut else original_key
    ctx.progress(state="processing")
    try:
        result = imaging.process(
            storage.path(source_key).read_bytes(),
            target,
            source_format=SOURCE_FORMATS.get(original_key.rsplit(".", 1)[-1]),
        )
        thumb = imaging.derived(result.data, THUMB)
        preview = imaging.derived(result.data, PREVIEW)
    except imaging.ProcessingError as exc:
        raise DomainError(422, exc.code, str(exc)) from exc
    steps = ([{"step": "remove_background", "model": cut["model"]}] if cut else []) + result.steps
    ctx.check()
    directory = original_key.rsplit("/", 1)[0]
    with ctx.runner.sessions() as s, s.begin():
        version = _begin(s, ctx)
        stored = _write(storage, f"{directory}/processed.{result.ext}", result.data)
        _write(storage, f"{directory}/{assets.DERIVED['thumb']}", thumb)
        _write(storage, f"{directory}/{assets.DERIVED['preview']}", preview)
        version.processing = {
            **(version.processing or {}),
            "steps": steps,
            "output": {
                **stored,
                "mime": result.mime,
                "ext": result.ext,
                "width": result.width,
                "height": result.height,
            },
            "finished_at": utcnow().isoformat(),
            "job_id": str(ctx.job_id),
        }
        s.flush()
        report = quality.run(s, storage, version, "system")
        assets.transition(
            s, version.id, "processing_succeeded", "system", data={"validation": report.summary}
        )
        return {
            "asset_id": str(version.asset_id),
            "versions": [str(version.id)],
            "validation": report.summary,
        }


handle_remove_background = _step(_remove_background)
handle_process = _step(_process)
HANDLERS: dict[str, Handler] = {
    "remove_background": handle_remove_background,
    "process": handle_process,
}
