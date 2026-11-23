"""References: validated uploads with a role, and their links (FR-025, FR-026).

Files live at ``projects/<project_id>/references/<reference_id>.<ext>`` (Storage-and-Backup);
the key never contains user input. A reference is archived, not deleted, so the styles,
characters, jobs and versions that used it keep the relationship (FR-026).
"""

import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from asset_studio.db import utcnow, uuid7
from asset_studio.errors import DomainError
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.projects.service import get_project
from asset_studio.modules.references.imaging import ImageError, sniff
from asset_studio.modules.references.models import ROLES, Reference, ReferenceLink
from asset_studio.modules.storage.local import LocalStorage
from asset_studio.modules.styles.service import get_character, get_style

MAX_BYTES = 30 * 1024 * 1024
MIN_SIDE, MAX_SIDE = 64, 8192


def _actor(actor: Actor) -> None:
    if actor not in ("user", "mcp"):
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "References are managed by the user or Claude.")


def _role(role: str) -> str:
    if role not in ROLES:
        raise DomainError(422, "REFERENCE_ROLE_UNKNOWN", f"Unknown reference role: {role}.")
    return role


def _display_name(name: str) -> str:
    # Keep the last path segment only and drop control characters; it is shown, never used.
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    clean = "".join(ch for ch in base if ch.isprintable()).strip()
    return clean[:200] or "reference"


def get_reference(session: Session, reference_id: uuid.UUID) -> Reference:
    ref = session.get(Reference, reference_id)
    if ref is None:
        raise DomainError(404, "REFERENCE_NOT_FOUND", "Reference not found.")
    return ref


def upload(
    session: Session,
    storage: LocalStorage,
    project_id: uuid.UUID,
    data: bytes,
    *,
    role: str,
    name: str,
    actor: Actor,
) -> Reference:
    """Validate and store one reference image (FR-025)."""
    _actor(actor)
    project = get_project(session, project_id)
    if project.archived_at is not None:
        raise DomainError(409, "PROJECT_ARCHIVED", "The project is archived.")
    _role(role)
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
    ref_id = uuid7()
    key = f"projects/{project.id}/references/{ref_id}.{info.ext}"
    stored = storage.put(key, io.BytesIO(data), max_bytes=MAX_BYTES)
    duplicate = session.scalar(
        select(Reference.id).where(
            Reference.project_id == project.id,
            Reference.sha256 == stored.sha256,
            Reference.archived_at.is_(None),
        )
    )
    if duplicate is not None:
        storage.delete_prefix(key)
        raise DomainError(
            409,
            "REFERENCE_DUPLICATE",
            "This image is already a reference in the project.",
            {"reference_id": str(duplicate)},
        )
    ref = Reference(
        id=ref_id,
        project_id=project.id,
        role=role,
        name=_display_name(name),
        storage_key=stored.key,
        sha256=stored.sha256,
        mime=info.mime,
        width=info.width,
        height=info.height,
        bytes=stored.bytes,
    )
    session.add(ref)
    session.flush()
    record(
        session,
        actor=actor,
        action="reference.uploaded",
        subject_type="reference",
        subject_id=ref.id,
        project_id=project.id,
        data={"role": role, "sha256": stored.sha256, "width": info.width, "height": info.height},
    )
    return ref


def list_references(
    session: Session,
    project_id: uuid.UUID,
    *,
    role: str | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> list[Reference]:
    get_project(session, project_id)
    q = select(Reference).where(Reference.project_id == project_id)
    if role is not None:
        q = q.where(Reference.role == _role(role))
    if target_type is not None and target_id is not None:
        q = q.join(ReferenceLink, ReferenceLink.reference_id == Reference.id).where(
            ReferenceLink.target_type == target_type, ReferenceLink.target_id == target_id
        )
    if not include_archived:
        q = q.where(Reference.archived_at.is_(None))
    return list(session.scalars(q.order_by(Reference.id.desc())))


def update(
    session: Session,
    reference_id: uuid.UUID,
    actor: Actor,
    *,
    role: str | None = None,
    name: str | None = None,
) -> Reference:
    _actor(actor)
    ref = get_reference(session, reference_id)
    changes: dict[str, str] = {}
    if role is not None and role != ref.role:
        changes["role"] = _role(role)
    if name is not None and _display_name(name) != ref.name:
        changes["name"] = _display_name(name)
    if not changes:
        return ref
    before = {"role": ref.role, "name": ref.name}
    for key, value in changes.items():
        setattr(ref, key, value)
    session.flush()
    record(
        session,
        actor=actor,
        action="reference.updated",
        subject_type="reference",
        subject_id=ref.id,
        project_id=ref.project_id,
        data={"from": {k: before[k] for k in changes}, "to": changes},
    )
    return ref


def set_archived(
    session: Session, reference_id: uuid.UUID, archived: bool, actor: Actor
) -> Reference:
    _actor(actor)
    ref = get_reference(session, reference_id)
    if (ref.archived_at is not None) == archived:
        return ref
    ref.archived_at = utcnow() if archived else None
    session.flush()
    record(
        session,
        actor=actor,
        action=f"reference.{'archived' if archived else 'restored'}",
        subject_type="reference",
        subject_id=ref.id,
        project_id=ref.project_id,
    )
    return ref


def _target_project(session: Session, target_type: str, target_id: uuid.UUID) -> uuid.UUID:
    if target_type == "style":
        style = get_style(session, target_id)
        if style.archived_at is not None:
            raise DomainError(409, "STYLE_ARCHIVED", "The style is archived.")
        return style.project_id
    if target_type == "character":
        character = get_character(session, target_id)
        if character.archived_at is not None:
            raise DomainError(409, "CHARACTER_ARCHIVED", "The character is archived.")
        return character.project_id
    # Jobs and versions are linked by the generation pipeline (WP-08), not by clients.
    raise DomainError(422, "LINK_TARGET_UNSUPPORTED", f"Cannot link to a {target_type}.")


def link(
    session: Session,
    reference_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    actor: Actor,
    *,
    weight: float = 1.0,
) -> ReferenceLink:
    """Attach a reference to a style or character, or change the weight of the link."""
    _actor(actor)
    ref = get_reference(session, reference_id)
    if ref.archived_at is not None:
        raise DomainError(409, "REFERENCE_ARCHIVED", "The reference is archived.")
    if _target_project(session, target_type, target_id) != ref.project_id:
        raise DomainError(422, "LINK_OTHER_PROJECT", "The target belongs to another project.")
    if not 0 <= weight <= 2:
        raise DomainError(422, "LINK_WEIGHT_INVALID", "The weight must be between 0 and 2.")
    row = session.scalar(
        select(ReferenceLink).where(
            ReferenceLink.reference_id == ref.id,
            ReferenceLink.target_type == target_type,
            ReferenceLink.target_id == target_id,
        )
    )
    if row is not None and row.weight == weight:
        return row
    if row is None:
        row = ReferenceLink(
            reference_id=ref.id, target_type=target_type, target_id=target_id, weight=weight
        )
        session.add(row)
    else:
        row.weight = weight
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:  # a concurrent request linked it first
        raise DomainError(409, "LINK_EXISTS", "The reference is already linked.") from exc
    record(
        session,
        actor=actor,
        action="reference.linked",
        subject_type="reference",
        subject_id=ref.id,
        project_id=ref.project_id,
        data={"target_type": target_type, "target_id": str(target_id), "weight": weight},
    )
    return row


def unlink(
    session: Session,
    reference_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    actor: Actor,
) -> None:
    _actor(actor)
    ref = get_reference(session, reference_id)
    if target_type not in ("style", "character"):
        # Job and version links are history (FR-026); they are never removed.
        raise DomainError(422, "LINK_TARGET_UNSUPPORTED", f"Cannot unlink from a {target_type}.")
    row = session.scalar(
        select(ReferenceLink).where(
            ReferenceLink.reference_id == ref.id,
            ReferenceLink.target_type == target_type,
            ReferenceLink.target_id == target_id,
        )
    )
    if row is None:
        raise DomainError(404, "LINK_NOT_FOUND", "The reference is not linked to this target.")
    session.delete(row)
    session.flush()
    record(
        session,
        actor=actor,
        action="reference.unlinked",
        subject_type="reference",
        subject_id=ref.id,
        project_id=ref.project_id,
        data={"target_type": target_type, "target_id": str(target_id)},
    )


def links_of(session: Session, reference_id: uuid.UUID) -> list[ReferenceLink]:
    get_reference(session, reference_id)
    return list(
        session.scalars(
            select(ReferenceLink)
            .where(ReferenceLink.reference_id == reference_id)
            .order_by(ReferenceLink.id)
        )
    )


@dataclass
class ReferenceFile:
    path: Path
    mime: str
    filename: str


def reference_file(
    session: Session, storage: LocalStorage, reference_id: uuid.UUID
) -> ReferenceFile:
    ref = get_reference(session, reference_id)
    try:
        path = storage.path(ref.storage_key)
    except FileNotFoundError as exc:
        raise DomainError(404, "FILE_NOT_AVAILABLE", "The file is not available.") from exc
    stem = ref.name.rsplit(".", 1)[0] or "reference"
    return ReferenceFile(
        path=path, mime=ref.mime, filename=f"{stem}.{ref.storage_key.rsplit('.', 1)[-1]}"
    )
