"""Model registry: catalogue, installed files, downloads, licences, compatibility.

- FR-080: the registry is the catalogue (``catalogue.json``) plus model files found on disk.
- FR-081: ``scan`` looks in the model folders (the ComfyUI ``models`` layout).
- FR-082 / RULE-008 / NFR-007: a download needs the user's confirmation of file, source and
  size; it resumes with HTTP ranges, is checked against the catalogue SHA-256 and only then
  moved into place.
- FR-083 / RULE-007: a licence that does not allow the project's intended use is a warning
  that needs an audited confirmation; it is never a block.
- FR-084 / RULE-015: LoRAs and other add-ons must match the checkpoint's family.
"""

import hashlib
import re
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from asset_studio.config import get_settings
from asset_studio.db import utcnow
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.jobs.models import Job
from asset_studio.modules.jobs.runner import JobContext
from asset_studio.modules.models import catalogue as cat
from asset_studio.modules.models.models import (
    Licence,
    LicenceAcknowledgement,
    Model,
    ModelFamily,
)
from asset_studio.modules.poses.detection import models_dir as pose_models_dir
from asset_studio.modules.projects.service import get_project

# ComfyUI's folder names, so the host's ComfyUI/models folder can be shared as is.
KIND_FOLDERS = {
    "checkpoint": "checkpoints",
    "lora": "loras",
    "controlnet": "controlnet",
    "ip_adapter": "ipadapter",
    "clip_vision": "clip_vision",
    "vae": "vae",
    "segmentation": "background_removal",
}
SUFFIXES = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx"}
# Kinds that must share the checkpoint's family (RULE-015).
FAMILY_BOUND = ("lora", "controlnet", "ip_adapter", "vae")
CHUNK = 1024 * 1024
PROGRESS_SECONDS = 2.0


def models_root() -> Path:
    settings = get_settings()
    return Path(settings.models_dir or Path(settings.data_dir) / "models")


def folder(kind: str) -> Path:
    if kind == "pose":
        return pose_models_dir()
    return models_root() / KIND_FOLDERS[kind]


def file_path(model: Model) -> Path:
    return folder(model.kind) / model.file_name


def get_model(session: Session, model_id: str, *, lock: bool = False) -> Model:
    q = select(Model).where(Model.id == model_id)
    if lock:
        q = q.with_for_update()
    model = session.scalar(q)
    if model is None:
        raise DomainError(404, "MODEL_NOT_FOUND", "Model not found.")
    return model


# --- catalogue and scan ----------------------------------------------------------------------


def sync_catalogue(session: Session, catalogue: cat.Catalogue | None = None) -> None:
    """Insert or update families, licences and catalogue models; keep install state."""
    c = catalogue or cat.load()
    for fam in c.families:
        row = session.get(ModelFamily, fam.id) or ModelFamily(id=fam.id)
        row.name = fam.name
        session.add(row)
    for lic in c.licences:
        lrow = session.get(Licence, lic.id) or Licence(id=lic.id)
        lrow.name, lrow.commercial_use, lrow.url, lrow.notes = (
            lic.name,
            lic.commercial_use,
            lic.url,
            lic.notes,
        )
        session.add(lrow)
    session.flush()
    for entry in c.models:
        model = session.get(Model, entry.id)
        if model is None:
            model = Model(id=entry.id, origin="catalogue", status="available")
            session.add(model)
        elif model.sha256 != entry.sha256:
            model.verification = "unverified"  # a new upstream file: check again
        model.name, model.kind, model.family_id = entry.name, entry.kind, entry.family
        model.licence_id, model.file_name, model.source_url = (
            entry.licence,
            entry.file_name,
            entry.source_url,
        )
        model.sha256, model.bytes, model.notes = entry.sha256, entry.bytes, entry.notes
        model.origin = "catalogue"
    session.flush()


def _active_jobs(session: Session, kind: str) -> dict[str, Job]:
    rows = session.scalars(
        select(Job).where(Job.kind == kind, Job.state.in_(("queued", "running")))
    )
    return {str(j.params.get("model_id")): j for j in rows}


def _local_id(session: Session, kind: str, file_name: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", Path(file_name).stem.lower()).strip("-")[:90] or "model"
    base = f"local-{kind.replace('_', '-')}-{stem}"
    candidate, n = base, 2
    while session.get(Model, candidate) is not None:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


@dataclass
class ScanResult:
    installed: int
    added: list[str]
    missing: list[str]


def _refresh(model: Model, downloading: bool) -> None:
    path = file_path(model)
    if path.is_file():
        size = path.stat().st_size
        if model.bytes is not None and model.origin == "catalogue" and size != model.bytes:
            model.verification = "mismatch"
        elif model.file_bytes != size:
            model.verification = "unverified"
        model.file_bytes, model.status = size, "installed"
    else:
        model.file_bytes = None
        model.status = (
            "downloading"
            if downloading
            else "available"
            if model.origin == "catalogue"
            else "missing"
        )


def reconcile(session: Session) -> None:
    """Fix statuses from the files and the queue (cheap: no hashing)."""
    active = _active_jobs(session, "download")
    for model in session.scalars(select(Model)):
        _refresh(model, model.id in active)
    session.flush()


def scan(session: Session, actor: Actor) -> ScanResult:
    """FR-081: find model files in the folders; unknown files become local models."""
    sync_catalogue(session)
    reconcile(session)
    known = {(m.kind, m.file_name) for m in session.scalars(select(Model))}
    added: list[str] = []
    for kind in (*KIND_FOLDERS, "pose"):
        base = folder(kind)
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUFFIXES:
                continue
            if (kind, path.name) in known:
                continue
            model = Model(
                id=_local_id(session, kind, path.name),
                name=path.name,
                kind=kind,
                family_id=None,
                licence_id="unknown",
                file_name=path.name,
                origin="local",
                status="installed",
                file_bytes=path.stat().st_size,
                notes="Found on disk; family and licence are not known.",
            )
            session.add(model)
            session.flush()
            added.append(model.id)
    rows = list(session.scalars(select(Model)))
    result = ScanResult(
        installed=sum(1 for m in rows if m.status == "installed"),
        added=added,
        missing=[m.id for m in rows if m.status == "missing"],
    )
    record(
        session,
        actor=actor,
        action="models.rescanned",
        subject_type="model",
        data={"installed": result.installed, "added": added, "missing": result.missing},
    )
    return result


def list_models(session: Session, kind: str | None = None) -> list[Model]:
    reconcile(session)
    q = select(Model).order_by(Model.kind, Model.origin, Model.name)
    if kind is not None:
        q = q.where(Model.kind == kind)
    return list(session.scalars(q))


def set_family(session: Session, model_id: str, family_id: str | None, actor: Actor) -> Model:
    """Only local files: the catalogue states the family of its models."""
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user changes model families.")
    model = get_model(session, model_id)
    if model.origin != "local":
        raise DomainError(409, "MODEL_FROM_CATALOGUE", "The catalogue sets this model's family.")
    if family_id is not None and session.get(ModelFamily, family_id) is None:
        raise DomainError(422, "FAMILY_UNKNOWN", f"Unknown model family: {family_id}.")
    if model.family_id != family_id:
        before, model.family_id = model.family_id, family_id
        session.flush()
        record(
            session,
            actor=actor,
            action="model.family_set",
            subject_type="model",
            data={"model_id": model.id, "from": before, "to": family_id},
        )
    return model


# --- licences (RULE-007, FR-083) -------------------------------------------------------------


@dataclass
class LicenceStatus:
    conflict: bool
    acknowledged: bool


def _conflicts(intended_use: str, licence: Licence) -> bool:
    return intended_use == "commercial" and licence.commercial_use != "allowed"


def licence_status(
    session: Session, project_id: uuid.UUID, models: Iterable[Model]
) -> dict[str, LicenceStatus]:
    project = get_project(session, project_id)
    acks = {
        (a.model_id, a.licence_id)
        for a in session.scalars(
            select(LicenceAcknowledgement).where(
                LicenceAcknowledgement.project_id == project.id,
                LicenceAcknowledgement.intended_use == project.intended_use,
            )
        )
    }
    out = {}
    for m in models:
        licence = session.get(Licence, m.licence_id)
        conflict = licence is not None and _conflicts(project.intended_use, licence)
        out[m.id] = LicenceStatus(conflict, conflict and (m.id, m.licence_id) in acks)
    return out


def acknowledge(
    session: Session, project_id: uuid.UUID, model_id: str, actor: Actor, note: str = ""
) -> LicenceAcknowledgement:
    """RULE-007: the user confirms using a model despite the licence; audited."""
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user confirms a licence warning.")
    sync_catalogue(session)
    project = get_project(session, project_id)
    model = get_model(session, model_id)
    status = licence_status(session, project.id, [model])[model.id]
    if not status.conflict:
        raise DomainError(409, "LICENCE_NO_CONFLICT", "This model's licence fits the project.")
    ack = LicenceAcknowledgement(
        project_id=project.id,
        model_id=model.id,
        licence_id=model.licence_id,
        intended_use=project.intended_use,
        actor=actor,
        note=note,
    )
    session.add(ack)
    session.flush()
    record(
        session,
        actor=actor,
        action="licence.acknowledged",
        subject_type="model",
        project_id=project.id,
        data={
            "model_id": model.id,
            "licence": model.licence_id,
            "intended_use": project.intended_use,
            "note": note,
        },
    )
    return ack


def licence_gate(session: Session, project_id: uuid.UUID, model_ids: Iterable[str]) -> None:
    """Raise unless every conflicting licence was confirmed for this project (WP-08 uses it)."""
    sync_catalogue(session)
    models = [get_model(session, mid) for mid in dict.fromkeys(model_ids)]
    status = licence_status(session, project_id, models)
    pending = [m.id for m in models if status[m.id].conflict and not status[m.id].acknowledged]
    if pending:
        raise DomainError(
            409,
            "LICENCE_CONFIRMATION_REQUIRED",
            "Confirm the licence warning for these models first.",
            {"models": pending},
        )


# --- compatibility (FR-084, RULE-015) --------------------------------------------------------


def compatibility(session: Session, model_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Problems that stop these models from being used together; empty means compatible."""
    sync_catalogue(session)
    models = [get_model(session, mid) for mid in dict.fromkeys(model_ids)]
    problems: list[dict[str, Any]] = []

    def add(code: str, model: Model | None, detail: str) -> None:
        problems.append({"code": code, "model_id": model.id if model else None, "detail": detail})

    reconcile(session)
    for m in models:
        if m.status != "installed":
            add("MODEL_NOT_INSTALLED", m, f"{m.name} is not installed.")
        elif m.verification == "mismatch":
            add("MODEL_CHECKSUM_MISMATCH", m, f"{m.name} does not match its checksum.")
    checkpoints = [m for m in models if m.kind == "checkpoint"]
    addons = [m for m in models if m.kind in FAMILY_BOUND]
    if addons and not checkpoints:
        add("CHECKPOINT_REQUIRED", None, "Choose a checkpoint for these add-ons.")
    if len(checkpoints) > 1:
        add("CHECKPOINT_MULTIPLE", None, "Choose one checkpoint.")
    if len(checkpoints) == 1:
        base = checkpoints[0]
        if base.family_id is None:
            add("FAMILY_UNKNOWN", base, f"The family of {base.name} is not known.")
        for m in addons:
            if m.family_id is None:
                add("FAMILY_UNKNOWN", m, f"The family of {m.name} is not known.")
            elif base.family_id is not None and m.family_id != base.family_id:
                add(
                    "FAMILY_MISMATCH",
                    m,
                    f"{m.name} is for {m.family_id}, the checkpoint is {base.family_id}.",
                )
    if any(m.kind == "ip_adapter" for m in models) and not any(
        m.kind == "clip_vision" for m in models
    ):
        add("CLIP_VISION_REQUIRED", None, "IP-Adapter needs a CLIP vision image encoder.")
    return problems


# --- downloads (FR-082, RULE-008, NFR-007) ---------------------------------------------------


def request_download(
    session: Session,
    model_id: str,
    actor: Actor,
    *,
    file_name: str,
    source_url: str,
    bytes_: int,
) -> Job:
    """Queue a download after the user confirmed exactly what will be fetched."""
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user approves a model download.")
    sync_catalogue(session)
    reconcile(session)
    model = get_model(session, model_id, lock=True)
    if model.origin != "catalogue" or not model.source_url or model.bytes is None:
        raise DomainError(409, "MODEL_NOT_DOWNLOADABLE", "This model has no download source.")
    expected = {"file_name": model.file_name, "source_url": model.source_url, "bytes": model.bytes}
    if (file_name, source_url, bytes_) != tuple(expected.values()):
        raise DomainError(
            409,
            "DOWNLOAD_CONFIRMATION_MISMATCH",
            "The confirmation does not match the catalogue entry.",
            {"expected": expected},
        )
    active = _active_jobs(session, "download").get(model.id)
    if active is not None:
        raise DomainError(
            409,
            "DOWNLOAD_IN_PROGRESS",
            "This model is already being downloaded.",
            {"job_id": str(active.id)},
        )
    if model.status == "installed" and model.verification != "mismatch":
        raise DomainError(409, "MODEL_ALREADY_INSTALLED", "This model is already installed.")
    job = jobs.enqueue(session, "download", {"model_id": model.id}, actor=actor)
    model.status = "downloading"
    session.flush()
    record(
        session,
        actor=actor,
        action="model.download_approved",
        subject_type="model",
        data={**expected, "model_id": model.id, "job_id": str(job.id)},
    )
    return job


def http_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=True)


_client_factory: Callable[[], httpx.Client] = http_client


def set_http_client_factory(factory: Callable[[], httpx.Client]) -> None:
    """Tests replace the HTTP client."""
    global _client_factory
    _client_factory = factory


def _sha256(path: Path, on_chunk: Callable[[int], None] | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
            if on_chunk:
                on_chunk(len(chunk))
    return digest.hexdigest()


class _Throttle:
    def __init__(self, ctx: JobContext, total: int, step: str) -> None:
        self.ctx, self.total, self.step, self.done, self.last = ctx, total, step, 0, 0.0

    def __call__(self, n: int) -> None:
        self.done += n
        now = time.monotonic()
        if now - self.last >= PROGRESS_SECONDS:
            self.last = now
            self.ctx.progress(state=self.step, bytes=self.done, of=self.total)
        else:
            self.ctx.check()  # cancellation still stops promptly


def _set(ctx: JobContext, model_id: str, **values: Any) -> None:
    with ctx.runner.sessions() as s, s.begin():
        model = get_model(s, model_id, lock=True)
        for key, value in values.items():
            setattr(model, key, value)


def handle_download(ctx: JobContext) -> dict[str, Any]:
    """Worker: resumable download to ``<file>.part``, SHA-256 check, then rename."""
    model_id = str(ctx.params["model_id"])
    with ctx.runner.sessions() as s:
        m = get_model(s, model_id)
        url, expected, total, target = m.source_url, m.sha256, m.bytes, file_path(m)
    if not url or not url.startswith("https://") or expected is None or total is None:
        raise DomainError(409, "MODEL_NOT_DOWNLOADABLE", "This model has no download source.")
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    try:
        offset = part.stat().st_size if part.exists() else 0
        if offset > total:
            part.unlink()
            offset = 0
        progress = _Throttle(ctx, total, "downloading")
        progress.done = offset
        if offset < total:
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            with _client_factory() as client, client.stream("GET", url, headers=headers) as r:
                if r.url.scheme != "https":
                    raise DomainError(502, "DOWNLOAD_FAILED", "The source redirected to HTTP.")
                if r.status_code == 200:
                    offset, progress.done, mode = 0, 0, "wb"  # no range support: restart
                elif r.status_code == 206:
                    mode = "ab"
                else:
                    raise DomainError(
                        502, "DOWNLOAD_FAILED", f"The source answered HTTP {r.status_code}."
                    )
                with part.open(mode) as out:
                    for chunk in r.iter_bytes(CHUNK):
                        out.write(chunk)
                        progress(len(chunk))
        if part.stat().st_size != total:
            raise DomainError(502, "DOWNLOAD_INCOMPLETE", "The download stopped early; retry it.")
        ctx.progress(state="verifying", bytes=total, of=total)
        if _sha256(part, _Throttle(ctx, total, "verifying")) != expected:
            part.unlink(missing_ok=True)
            raise DomainError(
                422, "CHECKSUM_MISMATCH", "The downloaded file does not match its checksum."
            )
        part.replace(target)
    except DomainError as exc:
        # A partial file stays for the next attempt, unless it was wrong.
        _set(ctx, model_id, status="available")
        raise exc
    except Exception:
        _set(ctx, model_id, status="available")
        raise
    _set(
        ctx,
        model_id,
        status="installed",
        file_bytes=total,
        verification="ok",
        verified_at=utcnow(),
    )
    return {"model_id": model_id, "bytes": total, "sha256": expected}


def request_verify(session: Session, model_id: str, actor: Actor) -> Job:
    """Queue a SHA-256 check of an installed file."""
    sync_catalogue(session)
    reconcile(session)
    model = get_model(session, model_id)
    if model.status != "installed":
        raise DomainError(409, "MODEL_NOT_INSTALLED", f"{model.name} is not installed.")
    if model.id in _active_jobs(session, "verify_model"):
        raise DomainError(409, "VERIFY_IN_PROGRESS", "This model is already being checked.")
    record(
        session,
        actor=actor,
        action="model.verify_requested",
        subject_type="model",
        data={"model_id": model.id},
    )
    return jobs.enqueue(session, "verify_model", {"model_id": model.id}, actor=actor)


def handle_verify_model(ctx: JobContext) -> dict[str, Any]:
    model_id = str(ctx.params["model_id"])
    with ctx.runner.sessions() as s:
        m = get_model(s, model_id)
        path, expected, origin = file_path(m), m.sha256, m.origin
    if not path.is_file():
        raise DomainError(409, "MODEL_NOT_INSTALLED", "The model file is not there.")
    size = path.stat().st_size
    actual = _sha256(path, _Throttle(ctx, size, "verifying"))
    if origin == "local" and expected is None:
        # A local file has no expected hash: remember it, so a later change is noticed.
        _set(ctx, model_id, sha256=actual, verification="ok", verified_at=utcnow(), file_bytes=size)
        return {"model_id": model_id, "sha256": actual, "match": True}
    match = actual == expected
    _set(
        ctx,
        model_id,
        verification="ok" if match else "mismatch",
        verified_at=utcnow(),
        file_bytes=size,
    )
    return {"model_id": model_id, "sha256": actual, "match": match}
