"""Generation: request, checks, queueing, the GPU job, and regeneration (FR-030-FR-038, FR-052).

A request names the project, the target asset and the inputs (style, character, pose,
reference or init image, prompt, models, parameters). ``plan`` resolves it into a workflow
and frozen engine inputs and lists anything that stops it (models, compatibility, RULE-015).
``queue`` also runs the licence gate (RULE-007), then queues one GPU job per variant and per
batch item (FR-034). The job renders the pose, uploads images, runs the engine and stores
each output as a new version with full metadata (RULE-011). Regenerating reuses a version's
stored request with changes, so the old version stays as it is (FR-052, AC-002).
"""

import hashlib
import io
import json
import secrets
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from asset_studio.errors import DomainError
from asset_studio.modules.assets import service as assets
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.jobs.models import Job
from asset_studio.modules.jobs.runner import JobContext
from asset_studio.modules.models import service as registry
from asset_studio.modules.models.models import Model
from asset_studio.modules.poses.render import openpose_png
from asset_studio.modules.poses.service import get_pose
from asset_studio.modules.processing import service as processing
from asset_studio.modules.projects.service import get_project
from asset_studio.modules.providers.base import GenerationRequest
from asset_studio.modules.providers.engine import get_engine_monitor, run_generation
from asset_studio.modules.references import service as references
from asset_studio.modules.references.imaging import ImageError, sniff
from asset_studio.modules.storage.local import LocalStorage, get_storage
from asset_studio.modules.styles.service import get_character, get_style
from asset_studio.modules.workflows.builtin import SAMPLERS, SCHEDULERS, Features, template

MAX_SEED = 2**53 - 1
Text = Annotated[str, Field(max_length=2000)]
Side = Annotated[int, Field(ge=256, le=2048)]
Sampler = Literal[
    "euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_sde", "ddim", "uni_pc"
]
Scheduler = Literal["normal", "karras", "exponential", "sgm_uniform", "simple"]
if set(get_args(Sampler)) != set(SAMPLERS) or set(get_args(Scheduler)) != set(SCHEDULERS):
    raise RuntimeError("sampler and scheduler lists differ from the workflows")
# Pose control models in order of preference (D-50: the full OpenPose ControlNet first).
PREFERRED = {
    "controlnet": ("controlnet-openpose-sdxl-xinsir", "control-lora-openpose-sdxl"),
    "vae": ("sdxl-vae-fp16-fix",),
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetTarget(_Strict):
    """An existing asset (a new version of it) or a new asset in a category."""

    asset_id: uuid.UUID | None = None
    category: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _one(self) -> "AssetTarget":
        if (self.asset_id is None) == (self.category is None):
            raise ValueError("give either asset_id or category (and name)")
        return self


class ReferenceInput(_Strict):
    reference_id: uuid.UUID
    weight: float = Field(default=0.6, ge=0, le=2)
    end: float = Field(default=1.0, ge=0.05, le=1)


class InitImage(_Strict):
    """Image-to-image (FR-031) from a reference or an existing version."""

    reference_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    denoise: float = Field(default=0.6, ge=0.05, le=1)

    @model_validator(mode="after")
    def _one(self) -> "InitImage":
        if (self.reference_id is None) == (self.version_id is None):
            raise ValueError("give either reference_id or version_id")
        return self


class BatchItem(_Strict):
    name: str = Field(min_length=1, max_length=200)
    prompt: Text = ""


class GenerationSpec(_Strict):
    project_id: uuid.UUID
    asset: AssetTarget
    checkpoint_id: str = Field(min_length=1, max_length=120)
    # Picked automatically from installed models of the checkpoint's family when empty.
    vae_id: str | None = None
    controlnet_id: str | None = None
    ip_adapter_id: str | None = None
    clip_vision_id: str | None = None
    style_id: uuid.UUID | None = None
    character_id: uuid.UUID | None = None
    pose_id: uuid.UUID | None = None
    pose_strength: float = Field(default=1.0, ge=0, le=2)
    pose_end: float = Field(default=1.0, ge=0.05, le=1)
    reference: ReferenceInput | None = None
    init: InitImage | None = None
    prompt: Text = ""
    negative: Text = ""
    seed: int | None = Field(default=None, ge=0, le=MAX_SEED)
    steps: int = Field(default=30, ge=1, le=150)
    cfg: float = Field(default=6.5, ge=1, le=30)
    sampler: Sampler = "dpmpp_2m"
    scheduler: Scheduler = "karras"
    width: Side = 1024
    height: Side = 1024
    variants: int = Field(default=1, ge=1, le=8)
    # FR-034: one new asset per item, e.g. one per exercise in a list.
    batch: list[BatchItem] = Field(default_factory=list, max_length=50)

    @field_validator("width", "height")
    @classmethod
    def _multiple_of_8(cls, value: int) -> int:
        if value % 8:
            raise ValueError("must be a multiple of 8")
        return value

    @model_validator(mode="after")
    def _batch_needs_new_assets(self) -> "GenerationSpec":
        if self.batch and self.asset.asset_id is not None:
            raise ValueError("a batch creates new assets; give a category, not asset_id")
        return self


# --- planning ----------------------------------------------------------------------------------


@dataclass
class Target:
    asset_id: uuid.UUID | None
    name: str
    prompt: str


@dataclass
class Plan:
    features: Features
    models: dict[str, Model]
    positive: list[str]  # one per target, in order
    negative: str
    targets: list[Target]
    problems: list[dict[str, Any]] = field(default_factory=list)
    licence_pending: list[str] = field(default_factory=list)
    frozen: dict[str, Any] = field(default_factory=dict)


def _join(*parts: str) -> str:
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _pick(session: Session, kind: str, family: str | None, chosen: str | None) -> Model | None:
    if chosen:
        return registry.get_model(session, chosen)
    rows = [
        m
        for m in session.scalars(select(Model).where(Model.kind == kind))
        if m.status == "installed"
        and m.verification != "mismatch"
        and (kind == "clip_vision" or m.family_id == family)
    ]
    order = PREFERRED.get(kind, ())
    rows.sort(key=lambda m: (order.index(m.id) if m.id in order else len(order), m.origin, m.id))
    return rows[0] if rows else None


def _same_project(row_project: uuid.UUID | None, project_id: uuid.UUID, code: str) -> None:
    if row_project is not None and row_project != project_id:
        raise DomainError(422, code, "It belongs to another project.")


def plan(session: Session, spec: GenerationSpec) -> Plan:
    """Resolve a request; raise for invalid ids, list problems for what is not ready."""
    project = get_project(session, spec.project_id)
    if project.archived_at is not None:
        raise DomainError(409, "PROJECT_ARCHIVED", "The project is archived.")
    registry.sync_catalogue(session)
    registry.reconcile(session)
    problems: list[dict[str, Any]] = []

    style = get_style(session, spec.style_id) if spec.style_id else None
    character = get_character(session, spec.character_id) if spec.character_id else None
    pose = get_pose(session, spec.pose_id) if spec.pose_id else None
    ref = references.get_reference(session, spec.reference.reference_id) if spec.reference else None
    for row, code in (
        (style, "STYLE_OTHER_PROJECT"),
        (character, "CHARACTER_OTHER_PROJECT"),
        (pose, "POSE_OTHER_PROJECT"),
        (ref, "REFERENCE_OTHER_PROJECT"),
    ):
        if row is not None:
            _same_project(row.project_id, project.id, code)
            if row.archived_at is not None:
                problems.append(
                    {
                        "code": "INPUT_ARCHIVED",
                        "model_id": None,
                        "detail": f"{type(row).__name__} is archived.",
                    }
                )
    init_key: str | None = None
    if spec.init is not None:
        if spec.init.reference_id is not None:
            init_ref = references.get_reference(session, spec.init.reference_id)
            _same_project(init_ref.project_id, project.id, "REFERENCE_OTHER_PROJECT")
            init_key = init_ref.storage_key
        else:
            assert spec.init.version_id is not None  # noqa: S101 - validated
            version = assets.get_version(session, spec.init.version_id)
            _same_project(
                assets.get_asset(session, version.asset_id).project_id,
                project.id,
                "VERSION_OTHER_PROJECT",
            )
            if version.storage_key is None:
                raise DomainError(410, "VERSION_DELETED", "The version file was deleted.")
            init_key = version.storage_key

    checkpoint = registry.get_model(session, spec.checkpoint_id)
    if checkpoint.kind != "checkpoint":
        raise DomainError(422, "MODEL_KIND_WRONG", f"{checkpoint.name} is not a checkpoint.")
    family = checkpoint.family_id
    models: dict[str, Model] = {"checkpoint": checkpoint}
    vae = _pick(session, "vae", family, spec.vae_id)
    if vae is not None:
        models["vae"] = vae
    wanted = []
    if pose is not None:
        wanted.append("controlnet")
    if ref is not None:
        wanted += ["ip_adapter", "clip_vision"]
    chosen = {
        "controlnet": spec.controlnet_id,
        "ip_adapter": spec.ip_adapter_id,
        "clip_vision": spec.clip_vision_id,
    }
    for kind in wanted:
        m = _pick(session, kind, family, chosen[kind])
        if m is None:
            problems.append(
                {
                    "code": "MODEL_REQUIRED",
                    "model_id": None,
                    "detail": f"Install a {kind} model for {family or 'this checkpoint'}.",
                }
            )
        elif m.kind != kind:
            raise DomainError(422, "MODEL_KIND_WRONG", f"{m.name} is not a {kind} model.")
        else:
            models[kind] = m
    problems += registry.compatibility(session, [m.id for m in models.values()])

    # Prompts: request, character, style (FR-035); negatives from the avoid lists.
    def describe() -> str:
        parts: list[str] = []
        if character is not None:
            traits = character.attributes.get("traits", {})
            parts += [
                character.description,
                *(f"{k.replace('_', ' ')}: {v}" for k, v in traits.items()),
            ]
        if style is not None:
            a = style.attributes
            extra = a.get("extra", {})
            parts += [
                a.get("description", ""),
                a.get("rendering", ""),
                a.get("lighting", ""),
                a.get("background", ""),
                *(f"{k.replace('_', ' ')}: {v}" for k, v in extra.items()),
            ]
        return _join(*parts)

    if spec.batch:
        targets = [Target(None, item.name, _join(spec.prompt, item.prompt)) for item in spec.batch]
    elif spec.asset.asset_id is not None:
        asset = assets.get_asset(session, spec.asset.asset_id)
        _same_project(asset.project_id, project.id, "ASSET_OTHER_PROJECT")
        targets = [Target(asset.id, asset.name, spec.prompt)]
    else:
        targets = [Target(None, spec.asset.name or "Untitled", spec.prompt)]
    context = describe()
    positive = [_join(t.prompt, context) for t in targets]
    if not all(positive):
        problems.append(
            {
                "code": "PROMPT_REQUIRED",
                "model_id": None,
                "detail": "Write a prompt, or choose a style or character.",
            }
        )
    avoid = [
        *(style.attributes.get("avoid", []) if style else []),
        *(character.attributes.get("avoid", []) if character else []),
    ]
    negative = _join(spec.negative, *avoid)

    features = Features(
        img2img=spec.init is not None,
        pose="controlnet" in models,
        reference="ip_adapter" in models and "clip_vision" in models,
        vae="vae" in models,
    )
    status = registry.licence_status(session, project.id, models.values())
    frozen = {
        "workflow": {"id": features.id, "version": template(features).version},
        "features": {
            "img2img": features.img2img,
            "pose": features.pose,
            "reference": features.reference,
            "vae": features.vae,
        },
        "models": {
            role: {"id": m.id, "file": m.file_name, "sha256": m.sha256, "family": m.family_id}
            for role, m in models.items()
        },
        "style": {"id": str(style.id), "version": style.version} if style else None,
        "character": {"id": str(character.id), "version": character.version} if character else None,
        "pose": {
            "id": str(pose.id),
            "keypoints": pose.keypoints,
            "aspect": pose.aspect,
            "keypoints_sha256": hashlib.sha256(json.dumps(pose.keypoints).encode()).hexdigest(),
        }
        if pose
        else None,
        "reference": {"id": str(ref.id), "key": ref.storage_key, "sha256": ref.sha256}
        if ref
        else None,
        "init": {"key": init_key, "denoise": spec.init.denoise} if spec.init and init_key else None,
    }
    return Plan(
        features=features,
        models=models,
        positive=positive,
        negative=negative,
        targets=targets,
        problems=problems,
        licence_pending=[mid for mid, s in status.items() if s.conflict and not s.acknowledged],
        frozen=frozen,
    )


# --- queueing ----------------------------------------------------------------------------------


@dataclass
class Queued:
    asset_ids: list[uuid.UUID]
    jobs: list[Job]


def queue(session: Session, spec: GenerationSpec, actor: Actor) -> Queued:
    if actor not in ("user", "mcp"):
        raise DomainError(
            403, "ACTOR_NOT_ALLOWED", "Generation is requested by the user or Claude."
        )
    p = plan(session, spec)
    if p.problems:
        raise DomainError(
            422,
            "GENERATION_NOT_READY",
            "Fix these problems before queueing.",
            {"problems": p.problems},
        )
    registry.licence_gate(session, spec.project_id, [m.id for m in p.models.values()])
    queued: list[Job] = []
    asset_ids: list[uuid.UUID] = []
    base_seed = spec.seed if spec.seed is not None else secrets.randbelow(2**32)
    for target, positive in zip(p.targets, p.positive, strict=True):
        if target.asset_id is None:
            asset = assets.create_asset(
                session,
                spec.project_id,
                category=spec.asset.category or "",
                name=target.name,
                actor="user" if actor == "user" else "system",
            )
            target_id = asset.id
        else:
            target_id = target.asset_id
        asset_ids.append(target_id)
        for variant in range(spec.variants):
            seed = (base_seed + variant) % (MAX_SEED + 1)
            # What regeneration replays: the request for this one asset and seed.
            replay = spec.model_copy(
                update={
                    "asset": AssetTarget(asset_id=target_id),
                    "batch": [],
                    "variants": 1,
                    "seed": seed,
                    "prompt": target.prompt,
                },
            )
            job = jobs.enqueue(
                session,
                "generate",
                {
                    "spec": replay.model_dump(mode="json"),
                    "plan": {
                        **p.frozen,
                        "asset_id": str(target_id),
                        "positive": positive,
                        "negative": p.negative,
                        "seed": seed,
                        "params": {
                            "steps": spec.steps,
                            "cfg": spec.cfg,
                            "sampler": spec.sampler,
                            "scheduler": spec.scheduler,
                            "width": spec.width,
                            "height": spec.height,
                            "pose_strength": spec.pose_strength,
                            "pose_end": spec.pose_end,
                            "reference_weight": spec.reference.weight if spec.reference else None,
                            "reference_end": spec.reference.end if spec.reference else None,
                        },
                    },
                },
                actor=actor,
                project_id=spec.project_id,
            )
            if spec.reference is not None:
                references.record_use(
                    session, spec.reference.reference_id, "job", job.id, spec.reference.weight
                )
            queued.append(job)
    record(
        session,
        actor=actor,
        action="generation.queued",
        subject_type="generation",
        project_id=spec.project_id,
        data={
            "workflow": p.frozen["workflow"],
            "assets": [str(a) for a in asset_ids],
            "jobs": [str(j.id) for j in queued],
        },
    )
    return Queued(asset_ids, queued)


def regenerate(
    session: Session, version_id: uuid.UUID, changes: dict[str, Any], actor: Actor
) -> Queued:
    """FR-052: a new version of the same asset from the stored request, with changes."""
    version = assets.get_version(session, version_id)
    if version.generation_job_id is None:
        raise DomainError(409, "VERSION_NOT_GENERATED", "This version was not generated here.")
    job = jobs.get_job(session, version.generation_job_id)
    stored = dict(job.params.get("spec") or {})
    if not stored:
        raise DomainError(409, "VERSION_NOT_GENERATED", "The request was not stored.")
    forbidden = {"project_id", "asset", "batch"} & set(changes)
    if forbidden:
        raise DomainError(
            422, "REGENERATE_FIELD_FIXED", f"Cannot change {', '.join(sorted(forbidden))}."
        )
    stored.update(changes)
    stored["asset"] = {"asset_id": str(version.asset_id)}
    stored.setdefault("variants", 1)
    try:
        spec = GenerationSpec.model_validate(stored)
    except ValueError as exc:
        raise DomainError(422, "REQUEST_INVALID", str(exc)[:500]) from exc
    return queue(session, spec, actor)


# --- the GPU job -------------------------------------------------------------------------------


def _image(storage: LocalStorage, key: str) -> bytes:
    return storage.path(key).read_bytes()


def handle_generate(ctx: JobContext) -> dict[str, Any]:
    p = ctx.params["plan"]
    storage = get_storage()
    features = Features(**p["features"])
    workflow = template(features)
    models, params = p["models"], p["params"]
    inputs: dict[str, Any] = {
        "checkpoint": models["checkpoint"]["file"],
        "prompt": p["positive"],
        "negative": p["negative"],
        "seed": p["seed"],
        "steps": params["steps"],
        "cfg": params["cfg"],
        "sampler": params["sampler"],
        "scheduler": params["scheduler"],
        "width": params["width"],
        "height": params["height"],
        "prefix": f"asset_studio/{str(ctx.job_id)[:8]}",
    }
    images: dict[str, bytes] = {}
    if features.vae:
        inputs["vae"] = models["vae"]["file"]
    if features.pose:
        inputs.update(
            controlnet=models["controlnet"]["file"],
            pose_strength=params["pose_strength"],
            pose_end=params["pose_end"],
        )
        pose = p["pose"]
        images["pose_image"] = openpose_png(
            pose["keypoints"], pose["aspect"], params["width"], params["height"]
        )
    if features.reference:
        inputs.update(
            ip_adapter=models["ip_adapter"]["file"],
            clip_vision=models["clip_vision"]["file"],
            reference_weight=params["reference_weight"],
            reference_end=params["reference_end"],
        )
        images["reference_image"] = _image(storage, p["reference"]["key"])
    if features.img2img:
        inputs["denoise"] = p["init"]["denoise"]
        images["init_image"] = _image(storage, p["init"]["key"])

    monitor = get_engine_monitor()
    health = monitor.health()
    ctx.progress(state="submitting")
    outputs = run_generation(monitor.provider, GenerationRequest(workflow, inputs, images), ctx)
    if not outputs:
        raise DomainError(502, "GENERATION_EMPTY", "The engine returned no image.")

    device = health.devices[0] if health.devices else None
    metadata = {
        # RULE-011: enough to reproduce the request, without promising identical pixels.
        "workflow": p["workflow"],
        "engine": {"name": health.engine, "version": health.version},
        "models": models,
        "loras": [],
        "prompt": p["positive"],
        "negative": p["negative"],
        "seed": p["seed"],
        **{k: params[k] for k in ("steps", "cfg", "sampler", "scheduler")},
        "size": {"width": params["width"], "height": params["height"]},
        "style": p["style"],
        "character": p["character"],
        "pose": {k: v for k, v in p["pose"].items() if k != "keypoints"}
        | {"strength": params["pose_strength"], "end": params["pose_end"]}
        if p["pose"]
        else None,
        "references": [
            {
                "id": p["reference"]["id"],
                "sha256": p["reference"]["sha256"],
                "weight": params["reference_weight"],
                "end": params["reference_end"],
            }
        ]
        if p["reference"]
        else [],
        "init": {"denoise": p["init"]["denoise"]} if p["init"] else None,
        "hardware": {"gpu": device.name, "vram_mb": device.vram_total_mb} if device else None,
        "job_id": str(ctx.job_id),
    }
    created: list[str] = []
    with ctx.runner.sessions() as s, s.begin():
        for out in outputs:
            try:
                info = sniff(out.data)
            except ImageError as exc:
                raise DomainError(
                    502, "GENERATION_OUTPUT_INVALID", "The engine output is not an image."
                ) from exc
            version = assets.add_version(
                s,
                storage,
                uuid.UUID(p["asset_id"]),
                io.BytesIO(out.data),
                mime=info.mime,
                actor="system",
                width=info.width,
                height=info.height,
                generation_job_id=ctx.job_id,
                generation_metadata=metadata,
            )
            if p["reference"]:
                references.record_use(
                    s,
                    uuid.UUID(p["reference"]["id"]),
                    "asset_version",
                    version.id,
                    params["reference_weight"],
                )
            # Post-processing and validation run next (FR-065, FR-060).
            processing.start(s, version.id, "system")
            created.append(str(version.id))
    return {"asset_id": p["asset_id"], "versions": created}
