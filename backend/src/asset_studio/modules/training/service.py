"""Training datasets, captions, estimates and runs (FR-070-FR-075, RULE-016, RULE-017).

Datasets hold approved versions of the project and images the user uploads; each image has a
caption the user can edit. A run freezes its parameters and an estimate measured on the
reference 6 GB GPU; SDXL on a GPU below the recommended VRAM needs the estimate to be
acknowledged first (RULE-016). Only the user changes datasets and starts runs.
"""

import io
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from asset_studio.db import utcnow
from asset_studio.errors import DomainError
from asset_studio.modules.assets.models import Asset, AssetVersion
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.jobs.models import Job
from asset_studio.modules.models.models import Model
from asset_studio.modules.models.service import get_model, reconcile, sync_catalogue
from asset_studio.modules.projects.service import get_project
from asset_studio.modules.references.imaging import ImageError, sniff
from asset_studio.modules.storage.local import LocalStorage
from asset_studio.modules.training.models import TrainingDataset, TrainingItem, TrainingRun

Family = Literal["sd15", "sdxl"]
# RULE-017: approved project assets; published ones were approved first.
USABLE_STATES = ("approved", "published")
MAX_BYTES = 30 * 1024 * 1024
MIN_SIDE, MAX_SIDE = 256, 8192
MIN_IMAGES, MAX_IMAGES = 5, 200
TRIGGER = re.compile(r"[a-z][a-z0-9_]{1,39}")


@dataclass(frozen=True)
class Preset:
    """Presets for small GPUs (ADR-011), with the speed measured on the 6 GB reference GPU:
    SD1.5 in this app (WP-13), SDXL in the prototype."""

    resolution: int
    seconds_per_step: float
    overhead_seconds: int
    recommended_vram_mb: int
    steps_per_image: int
    min_steps: int
    max_steps: int


PRESETS: dict[str, Preset] = {
    "sd15": Preset(512, 0.8, 90, 6_000, 100, 300, 3_000),
    "sdxl": Preset(768, 30.0, 180, 12_000, 60, 300, 3_000),
}


def _user(actor: Actor) -> None:
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user prepares and starts training.")


# --- datasets -----------------------------------------------------------------------------


def list_datasets(
    session: Session, project_id: uuid.UUID, archived: bool = False
) -> list[tuple[TrainingDataset, int]]:
    get_project(session, project_id)
    counts = (
        select(TrainingItem.dataset_id, func.count().label("n"))
        .group_by(TrainingItem.dataset_id)
        .subquery()
    )
    q = (
        select(TrainingDataset, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.dataset_id == TrainingDataset.id)
        .where(TrainingDataset.project_id == project_id)
        .order_by(TrainingDataset.created_at.desc())
    )
    if not archived:
        q = q.where(TrainingDataset.archived_at.is_(None))
    return [(d, int(n)) for d, n in session.execute(q)]


def get_dataset(session: Session, dataset_id: uuid.UUID) -> TrainingDataset:
    dataset = session.get(TrainingDataset, dataset_id)
    if dataset is None:
        raise DomainError(404, "DATASET_NOT_FOUND", "Training dataset not found.")
    return dataset


def _trigger(word: str) -> str:
    word = word.strip().lower()
    if not TRIGGER.fullmatch(word):
        raise DomainError(
            422,
            "TRIGGER_WORD_INVALID",
            "The trigger word is 2-40 lowercase letters, digits or _, starting with a letter.",
        )
    return word


def create_dataset(
    session: Session, project_id: uuid.UUID, name: str, trigger_word: str, actor: Actor
) -> TrainingDataset:
    _user(actor)
    project = get_project(session, project_id)
    if project.archived_at is not None:
        raise DomainError(409, "PROJECT_ARCHIVED", "The project is archived.")
    dataset = TrainingDataset(
        project_id=project.id, name=name.strip()[:120], trigger_word=_trigger(trigger_word)
    )
    session.add(dataset)
    session.flush()
    record(
        session,
        actor=actor,
        action="training_dataset.created",
        subject_type="training_dataset",
        subject_id=dataset.id,
        project_id=project.id,
        data={"name": dataset.name, "trigger_word": dataset.trigger_word},
    )
    return dataset


def update_dataset(
    session: Session,
    dataset_id: uuid.UUID,
    actor: Actor,
    *,
    name: str | None = None,
    trigger_word: str | None = None,
    archived: bool | None = None,
) -> TrainingDataset:
    _user(actor)
    dataset = get_dataset(session, dataset_id)
    if name is not None:
        dataset.name = name.strip()[:120]
    if trigger_word is not None:
        dataset.trigger_word = _trigger(trigger_word)
    if archived is not None:
        dataset.archived_at = utcnow() if archived else None
    session.flush()
    record(
        session,
        actor=actor,
        action="training_dataset.updated",
        subject_type="training_dataset",
        subject_id=dataset.id,
        project_id=dataset.project_id,
        data={"name": name, "trigger_word": trigger_word, "archived": archived},
    )
    return dataset


def _open(dataset: TrainingDataset) -> None:
    if dataset.archived_at is not None:
        raise DomainError(409, "DATASET_ARCHIVED", "The dataset is archived.")


def list_items(session: Session, dataset_id: uuid.UUID) -> list[TrainingItem]:
    get_dataset(session, dataset_id)
    q = (
        select(TrainingItem)
        .where(TrainingItem.dataset_id == dataset_id)
        .order_by(TrainingItem.created_at, TrainingItem.id)
    )
    return list(session.scalars(q))


def _count(session: Session, dataset_id: uuid.UUID) -> int:
    return session.scalar(select(func.count()).where(TrainingItem.dataset_id == dataset_id)) or 0


def _room(session: Session, dataset_id: uuid.UUID, adding: int) -> None:
    if _count(session, dataset_id) + adding > MAX_IMAGES:
        raise DomainError(422, "DATASET_FULL", f"A dataset holds at most {MAX_IMAGES} images.")


def add_versions(
    session: Session, dataset_id: uuid.UUID, version_ids: list[uuid.UUID], actor: Actor
) -> list[TrainingItem]:
    """FR-070 / RULE-017: approved (or published) versions of the dataset's project."""
    _user(actor)
    dataset = get_dataset(session, dataset_id)
    _open(dataset)
    rows = session.execute(
        select(AssetVersion, Asset)
        .join(Asset, Asset.id == AssetVersion.asset_id)
        .where(AssetVersion.id.in_(version_ids))
    ).all()
    found = {v.id for v, _ in rows}
    missing = [str(v) for v in version_ids if v not in found]
    if missing:
        raise DomainError(404, "VERSION_NOT_FOUND", "Version not found.", {"missing": missing})
    have = set(
        session.scalars(select(TrainingItem.sha256).where(TrainingItem.dataset_id == dataset.id))
    )
    added: list[TrainingItem] = []
    for version, asset in rows:
        if asset.project_id != dataset.project_id:
            raise DomainError(
                409, "VERSION_OTHER_PROJECT", "The version belongs to another project."
            )
        if version.state not in USABLE_STATES or version.storage_key is None:
            raise DomainError(
                409,
                "VERSION_NOT_APPROVED",
                "Only approved or published versions can be used for training (RULE-017).",
                {"version_id": str(version.id), "state": version.state},
            )
        if version.sha256 in have:
            continue  # already in the dataset
        have.add(version.sha256)
        added.append(
            TrainingItem(
                dataset_id=dataset.id,
                source="asset_version",
                asset_version_id=version.id,
                storage_key=version.storage_key,
                sha256=version.sha256,
                width=version.width or 0,
                height=version.height or 0,
                caption=asset.name,
            )
        )
    _room(session, dataset.id, len(added))
    session.add_all(added)
    session.flush()
    if added:
        record(
            session,
            actor=actor,
            action="training_dataset.items_added",
            subject_type="training_dataset",
            subject_id=dataset.id,
            project_id=dataset.project_id,
            data={"versions": [str(i.asset_version_id) for i in added]},
        )
    return added


def upload(
    session: Session,
    storage: LocalStorage,
    dataset_id: uuid.UUID,
    data: bytes,
    *,
    caption: str,
    actor: Actor,
) -> TrainingItem:
    """FR-070 / RULE-017: an image the user uploads, checked like any upload (FR-025)."""
    _user(actor)
    dataset = get_dataset(session, dataset_id)
    _open(dataset)
    if len(data) > MAX_BYTES:
        raise DomainError(413, "FILE_TOO_LARGE", "The file is larger than 30 MB.")
    try:
        info = sniff(data)
    except ImageError as exc:
        raise DomainError(
            415, "MEDIA_TYPE_UNSUPPORTED", "Upload a PNG, JPEG or WebP image."
        ) from exc
    if min(info.width, info.height) < MIN_SIDE or max(info.width, info.height) > MAX_SIDE:
        raise DomainError(
            422,
            "IMAGE_SIZE_OUT_OF_RANGE",
            f"Each side must be between {MIN_SIDE} and {MAX_SIDE} pixels.",
            {"width": info.width, "height": info.height},
        )
    _room(session, dataset.id, 1)
    item_id = uuid.uuid4()
    key = f"projects/{dataset.project_id}/training/{dataset.id}/{item_id}.{info.ext}"
    stored = storage.put(key, io.BytesIO(data), max_bytes=MAX_BYTES)
    exists = session.scalar(
        select(TrainingItem.id).where(
            TrainingItem.dataset_id == dataset.id, TrainingItem.sha256 == stored.sha256
        )
    )
    if exists is not None:
        storage.delete_prefix(key)
        raise DomainError(409, "IMAGE_DUPLICATE", "This image is already in the dataset.")
    item = TrainingItem(
        id=item_id,
        dataset_id=dataset.id,
        source="upload",
        storage_key=key,
        sha256=stored.sha256,
        width=info.width,
        height=info.height,
        caption=caption.strip()[:1000],
    )
    session.add(item)
    session.flush()
    record(
        session,
        actor=actor,
        action="training_dataset.image_uploaded",
        subject_type="training_dataset",
        subject_id=dataset.id,
        project_id=dataset.project_id,
        data={"item_id": str(item.id), "sha256": stored.sha256},
    )
    return item


def get_item(session: Session, item_id: uuid.UUID) -> TrainingItem:
    item = session.get(TrainingItem, item_id)
    if item is None:
        raise DomainError(404, "TRAINING_ITEM_NOT_FOUND", "Dataset image not found.")
    return item


def set_caption(session: Session, item_id: uuid.UUID, caption: str, actor: Actor) -> TrainingItem:
    """FR-071: captions describe the image; the trigger word is added when training."""
    _user(actor)
    item = get_item(session, item_id)
    _open(get_dataset(session, item.dataset_id))
    item.caption = caption.strip()[:1000]
    session.flush()
    return item


def remove_item(session: Session, storage: LocalStorage, item_id: uuid.UUID, actor: Actor) -> None:
    _user(actor)
    item = get_item(session, item_id)
    dataset = get_dataset(session, item.dataset_id)
    _open(dataset)
    session.delete(item)
    session.flush()
    if item.source == "upload":
        storage.delete_prefix(item.storage_key)
    record(
        session,
        actor=actor,
        action="training_dataset.item_removed",
        subject_type="training_dataset",
        subject_id=dataset.id,
        project_id=dataset.project_id,
        data={"item_id": str(item.id), "source": item.source},
    )


# --- estimates and runs (FR-072, FR-073, RULE-016) ---------------------------------------------


def default_steps(family: str, images: int) -> int:
    p = PRESETS[family]
    return max(p.min_steps, min(p.max_steps, images * p.steps_per_image))


def estimate(family: str, steps: int, vram_mb: int | None) -> dict[str, Any]:
    """Time measured on the reference 6 GB GPU. SDXL below the recommended VRAM gets a
    warning that must be acknowledged before starting (RULE-016)."""
    p = PRESETS[family]
    weak = vram_mb is None or vram_mb < p.recommended_vram_mb
    return {
        "family": family,
        "steps": steps,
        "resolution": p.resolution,
        "seconds": round(p.overhead_seconds + steps * p.seconds_per_step),
        "seconds_per_step": p.seconds_per_step,
        "vram_mb": vram_mb,
        "recommended_vram_mb": p.recommended_vram_mb,
        "warning": family == "sdxl" and weak,
    }


def _base_model(session: Session, model_id: str, family: str) -> Model:
    sync_catalogue(session)
    reconcile(session)  # status from the files on disk
    model = get_model(session, model_id)
    if model.kind != "checkpoint" or model.family_id != family:
        raise DomainError(
            422,
            "BASE_MODEL_INVALID",
            f"Choose an installed {family.upper()} checkpoint as the base model.",
        )
    if model.status != "installed":
        raise DomainError(409, "MODEL_NOT_INSTALLED", f"{model.name} is not installed.")
    return model


def vae_for(session: Session, family: str) -> Model | None:
    """SDXL trains with the fp16-safe VAE when it is installed (prototype preset)."""
    if family != "sdxl":
        return None
    q = select(Model).where(
        Model.kind == "vae", Model.family_id == family, Model.status == "installed"
    )
    return session.scalars(q.order_by(Model.origin, Model.id)).first()


@dataclass
class RunRequest:
    dataset_id: uuid.UUID
    family: Family
    base_model_id: str
    steps: int | None = None
    network_dim: int = 16
    network_alpha: int = 8
    learning_rate: float = 1e-4
    seed: int = 42


def plan(
    session: Session, req: RunRequest, vram_mb: int | None
) -> tuple[TrainingDataset, Model, int, dict[str, Any]]:
    dataset = get_dataset(session, req.dataset_id)
    _open(dataset)
    images = _count(session, dataset.id)
    if images < MIN_IMAGES:
        raise DomainError(
            422,
            "DATASET_TOO_SMALL",
            f"A dataset needs at least {MIN_IMAGES} images.",
            {"images": images, "min": MIN_IMAGES},
        )
    model = _base_model(session, req.base_model_id, req.family)
    p = PRESETS[req.family]
    steps = req.steps or default_steps(req.family, images)
    if not p.min_steps <= steps <= p.max_steps:
        raise DomainError(
            422, "STEPS_OUT_OF_RANGE", f"Steps must be between {p.min_steps} and {p.max_steps}."
        )
    return dataset, model, images, estimate(req.family, steps, vram_mb)


def _active_run(session: Session, project_id: uuid.UUID) -> bool:
    q = (
        select(func.count())
        .select_from(TrainingRun)
        .join(Job, Job.id == TrainingRun.job_id)
        .where(Job.state.in_(("queued", "running")), TrainingRun.project_id == project_id)
    )
    return bool(session.scalar(q))


def start_run(
    session: Session,
    req: RunRequest,
    *,
    vram_mb: int | None,
    acknowledged_estimate: bool,
    actor: Actor,
) -> TrainingRun:
    _user(actor)
    dataset, model, images, est = plan(session, req, vram_mb)
    if est["warning"] and not acknowledged_estimate:
        raise DomainError(
            409,
            "ESTIMATE_NOT_ACKNOWLEDGED",
            "SDXL training on this GPU takes long. Confirm the estimate to start (RULE-016).",
            {"estimate": est},
        )
    if _active_run(session, dataset.project_id):
        raise DomainError(409, "TRAINING_ALREADY_QUEUED", "A training run is already queued.")
    run_id = uuid.uuid4()
    run = TrainingRun(
        id=run_id,
        project_id=dataset.project_id,
        dataset_id=dataset.id,
        family_id=req.family,
        base_model_id=model.id,
        params={
            "resolution": PRESETS[req.family].resolution,
            "steps": est["steps"],
            "network_dim": req.network_dim,
            "network_alpha": req.network_alpha,
            "learning_rate": req.learning_rate,
            "seed": req.seed,
            "trigger_word": dataset.trigger_word,
        },
        images=images,
        estimate=est,
        acknowledged_estimate=acknowledged_estimate,
        output_name=f"{dataset.trigger_word.replace('_', '-')}-{req.family}-{run_id.hex[:8]}",
        created_by_actor=actor,
    )
    session.add(run)
    session.flush()
    job = jobs.enqueue(
        session, "train", {"run_id": str(run.id)}, actor=actor, project_id=dataset.project_id
    )
    run.job_id = job.id
    record(
        session,
        actor=actor,
        action="training_run.started",
        subject_type="training_run",
        subject_id=run.id,
        project_id=dataset.project_id,
        data={
            "dataset_id": str(dataset.id),
            "family": req.family,
            "base_model": model.id,
            "steps": est["steps"],
            "estimate_seconds": est["seconds"],
            "acknowledged_estimate": acknowledged_estimate,
        },
    )
    return run


def list_runs(session: Session, project_id: uuid.UUID) -> list[TrainingRun]:
    get_project(session, project_id)
    q = (
        select(TrainingRun)
        .where(TrainingRun.project_id == project_id)
        .order_by(TrainingRun.created_at.desc())
        .limit(50)
    )
    return list(session.scalars(q))


def get_run(session: Session, run_id: uuid.UUID) -> TrainingRun:
    run = session.get(TrainingRun, run_id)
    if run is None:
        raise DomainError(404, "TRAINING_RUN_NOT_FOUND", "Training run not found.")
    return run
