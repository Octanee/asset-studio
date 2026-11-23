"""Poses: the library (built-in and project poses), edits, and detection jobs (FR-020-022).

Built-in poses are read-only; to change one, the user saves a copy into the project. A
detection job only proposes a skeleton: the user reviews it in the editor and saves it as a
pose with ``source = 'detected'`` (AC-011).
"""

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from asset_studio.db import utcnow
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.jobs.models import Job
from asset_studio.modules.jobs.runner import JobContext
from asset_studio.modules.poses.detection import Box, get_detector
from asset_studio.modules.poses.models import Pose
from asset_studio.modules.poses.skeleton import VIEWS, Point, visible
from asset_studio.modules.projects.service import get_project
from asset_studio.modules.references.service import get_reference
from asset_studio.modules.storage.local import get_storage

MIN_JOINTS = 4


def _actor(actor: Actor) -> None:
    if actor not in ("user", "mcp"):
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Poses are edited by the user or Claude.")


def _check(view: str, keypoints: list[Point]) -> list[list[float] | None]:
    if view not in VIEWS:
        raise DomainError(422, "POSE_VIEW_UNKNOWN", f"Unknown view: {view}.")
    if visible(keypoints) < MIN_JOINTS:
        raise DomainError(
            422, "POSE_TOO_FEW_JOINTS", f"A pose needs at least {MIN_JOINTS} visible joints."
        )
    return [None if p is None else [round(v, 4) for v in p] for p in keypoints]


def get_pose(session: Session, pose_id: uuid.UUID) -> Pose:
    pose = session.get(Pose, pose_id)
    if pose is None:
        raise DomainError(404, "POSE_NOT_FOUND", "Pose not found.")
    return pose


def list_poses(
    session: Session,
    project_id: uuid.UUID | None,
    *,
    view: str | None = None,
    include_archived: bool = False,
) -> list[Pose]:
    """Built-in poses first, then the project's poses (FR-020)."""
    q = select(Pose)
    if project_id is None:
        q = q.where(Pose.project_id.is_(None))
    else:
        get_project(session, project_id)
        q = q.where(or_(Pose.project_id.is_(None), Pose.project_id == project_id))
    if view is not None:
        q = q.where(Pose.view == view)
    if not include_archived:
        q = q.where(Pose.archived_at.is_(None))
    return list(session.scalars(q.order_by(Pose.project_id.is_not(None), Pose.name)))


def _source_reference(
    session: Session, project_id: uuid.UUID, reference_id: uuid.UUID | None
) -> uuid.UUID | None:
    if reference_id is None:
        return None
    if get_reference(session, reference_id).project_id != project_id:
        raise DomainError(422, "REFERENCE_OTHER_PROJECT", "The reference is in another project.")
    return reference_id


def create_pose(
    session: Session,
    project_id: uuid.UUID,
    *,
    name: str,
    view: str,
    aspect: float,
    keypoints: list[Point],
    actor: Actor,
    source_reference_id: uuid.UUID | None = None,
) -> Pose:
    """Save a pose from the editor; with a source reference it counts as detected (FR-022)."""
    _actor(actor)
    project = get_project(session, project_id)
    if project.archived_at is not None:
        raise DomainError(409, "PROJECT_ARCHIVED", "The project is archived.")
    pose = Pose(
        project_id=project.id,
        name=name.strip(),
        view=view,
        aspect=aspect,
        keypoints=_check(view, keypoints),
        source="detected" if source_reference_id else "editor",
        source_reference_id=_source_reference(session, project.id, source_reference_id),
    )
    session.add(pose)
    session.flush()
    record(
        session,
        actor=actor,
        action="pose.created",
        subject_type="pose",
        subject_id=pose.id,
        project_id=project.id,
        data={"name": pose.name, "source": pose.source},
    )
    return pose


def _editable(session: Session, pose_id: uuid.UUID) -> Pose:
    pose = get_pose(session, pose_id)
    if pose.project_id is None:
        raise DomainError(
            409, "POSE_BUILTIN_READONLY", "Built-in poses cannot be changed; save a copy."
        )
    return pose


def update_pose(
    session: Session,
    pose_id: uuid.UUID,
    actor: Actor,
    *,
    name: str | None = None,
    view: str | None = None,
    aspect: float | None = None,
    keypoints: list[Point] | None = None,
) -> Pose:
    _actor(actor)
    pose = _editable(session, pose_id)
    if pose.archived_at is not None:
        raise DomainError(409, "POSE_ARCHIVED", "The pose is archived.")
    new_view = view if view is not None else pose.view
    changes: dict[str, Any] = {}
    if name is not None and name.strip() != pose.name:
        changes["name"] = name.strip()
    if view is not None and view != pose.view:
        changes["view"] = view
    if aspect is not None and aspect != pose.aspect:
        changes["aspect"] = aspect
    if keypoints is not None or "view" in changes:
        checked = _check(new_view, keypoints if keypoints is not None else pose.keypoints)
        if checked != pose.keypoints:
            changes["keypoints"] = checked
    if not changes:
        return pose
    for key, value in changes.items():
        setattr(pose, key, value)
    session.flush()
    record(
        session,
        actor=actor,
        action="pose.updated",
        subject_type="pose",
        subject_id=pose.id,
        project_id=pose.project_id,
        data={"changed": sorted(changes)},
    )
    return pose


def set_archived(session: Session, pose_id: uuid.UUID, archived: bool, actor: Actor) -> Pose:
    _actor(actor)
    pose = _editable(session, pose_id)
    if (pose.archived_at is not None) == archived:
        return pose
    pose.archived_at = utcnow() if archived else None
    session.flush()
    record(
        session,
        actor=actor,
        action=f"pose.{'archived' if archived else 'restored'}",
        subject_type="pose",
        subject_id=pose.id,
        project_id=pose.project_id,
    )
    return pose


def request_detection(
    session: Session, reference_id: uuid.UUID, actor: Actor, *, box: Box | None = None
) -> Job:
    """Queue a ``detect_pose`` job on the CPU lane (FR-022)."""
    _actor(actor)
    ref = get_reference(session, reference_id)
    if ref.archived_at is not None:
        raise DomainError(409, "REFERENCE_ARCHIVED", "The reference is archived.")
    if box is not None and not (box[0] < box[2] and box[1] < box[3]):
        raise DomainError(422, "POSE_BOX_INVALID", "The box must have a positive size.")
    return jobs.enqueue(
        session,
        "detect_pose",
        {"reference_id": str(ref.id), "box": list(box) if box else None},
        actor=actor,
        project_id=ref.project_id,
    )


def handle_detect_pose(ctx: JobContext) -> dict[str, Any]:
    """Worker handler: run the detector and return the proposed skeleton as the job result."""
    detector = get_detector()
    if detector is None:
        raise DomainError(
            409,
            "POSE_DETECTOR_NOT_INSTALLED",
            "Pose detection is not installed. Set the pose by hand in the editor.",
        )
    reference_id = uuid.UUID(ctx.params["reference_id"])
    with ctx.runner.sessions() as s:
        ref = get_reference(s, reference_id)
        path, aspect = get_storage().path(ref.storage_key), ref.width / ref.height
    box = ctx.params.get("box")
    ctx.progress(state="detecting")
    found = detector.detect(path.read_bytes(), tuple(box) if box else None)
    if found is None:
        raise DomainError(
            422,
            "POSE_NOT_FOUND",
            "No person was found. Draw a box around the figure or set the pose by hand.",
        )
    return {
        "reference_id": str(reference_id),
        "detector": detector.name,
        "aspect": round(aspect, 4),
        "keypoints": [None if p is None else list(p) for p in found.keypoints],
        "score": round(found.score, 3),
        "box": list(found.box),
    }
