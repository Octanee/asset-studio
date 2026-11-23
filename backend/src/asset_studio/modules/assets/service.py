"""Asset service: assets, immutable versions, lifecycle transitions, files.

Business rules enforced here: RULE-003 (a version file is written once, a new file is a new
version), RULE-005 (MCP decisions only when the project allows), RULE-006 (every change is
audited), RULE-019 (permanent deletion keeps the rows and the audit trail), RULE-020
(withdrawing approval needs a reason and a never-published version).
"""

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import Select, exists, func, select
from sqlalchemy.orm import Session

from asset_studio.db import utcnow
from asset_studio.errors import DomainError
from asset_studio.modules.assets.lifecycle import TRANSITIONS, actor_allowed
from asset_studio.modules.assets.models import (
    Asset,
    AssetVersion,
    CollectionItem,
    StateTransition,
)
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.projects.service import current_config, get_project
from asset_studio.modules.storage.local import KeyExistsError, LocalStorage

MIME_EXT = {"image/png": "png", "image/webp": "webp", "image/jpeg": "jpg", "image/svg+xml": "svg"}
MAX_VERSION_BYTES = 200 * 1024 * 1024
DERIVED = {"thumb": "thumb-256.webp", "preview": "preview-1024.webp"}
MAX_TAGS, MAX_TAG = 20, 40
SORTS = ("newest", "oldest", "name", "updated")


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:70] or "asset"


def version_dir(project_id: uuid.UUID, asset_id: uuid.UUID, number: int) -> str:
    return f"projects/{project_id}/assets/{asset_id}/v{number}"


def _lock_version(session: Session, version_id: uuid.UUID) -> AssetVersion:
    version = session.scalar(
        select(AssetVersion)
        .where(AssetVersion.id == version_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if version is None:
        raise DomainError(404, "VERSION_NOT_FOUND", "Version not found.")
    return version


def _not_allowed(version: AssetVersion, action: str, detail: str) -> DomainError:
    return DomainError(
        409,
        "LIFECYCLE_TRANSITION_NOT_ALLOWED",
        detail,
        {"state": version.state, "action": action},
    )


# --- assets -----------------------------------------------------------------------------


def get_asset(session: Session, asset_id: uuid.UUID) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise DomainError(404, "ASSET_NOT_FOUND", "Asset not found.")
    return asset


def create_asset(
    session: Session, project_id: uuid.UUID, *, category: str, name: str, actor: Actor
) -> Asset:
    if actor not in ("user", "system"):
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Assets are created by the user or a job.")
    project = get_project(session, project_id)
    if project.archived_at is not None:
        raise DomainError(409, "PROJECT_ARCHIVED", "The project is archived.")
    if category not in {c.slug for c in current_config(session, project).categories}:
        raise DomainError(422, "CATEGORY_UNKNOWN", "The category is not defined in the project.")
    base = slug = _slugify(name)
    n = 2
    while session.scalar(
        select(func.count()).where(Asset.project_id == project_id, Asset.slug == slug)
    ):
        slug, n = f"{base}-{n}", n + 1
    asset = Asset(project_id=project_id, category=category, slug=slug, name=name[:200])
    session.add(asset)
    session.flush()
    record(
        session,
        actor=actor,
        action="asset.created",
        subject_type="asset",
        subject_id=asset.id,
        project_id=project_id,
        data={"slug": slug, "category": category},
    )
    return asset


def set_asset_archived(
    session: Session, asset_id: uuid.UUID, archived: bool, actor: Actor
) -> Asset:
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user can archive or restore assets.")
    asset = get_asset(session, asset_id)
    if (asset.archived_at is not None) != archived:
        asset.archived_at = utcnow() if archived else None
        record(
            session,
            actor=actor,
            action="asset.archived" if archived else "asset.restored",
            subject_type="asset",
            subject_id=asset.id,
            project_id=asset.project_id,
        )
    return asset


def normalise_tags(tags: list[str]) -> list[str]:
    """Lower case, words joined by ``-``, unique, in the given order (FR-049)."""
    out: list[str] = []
    for tag in tags:
        t = re.sub(r"[^\w]+", "-", tag.strip().lower()).strip("-")[:MAX_TAG]
        if t and t not in out:
            out.append(t)
    if len(out) > MAX_TAGS:
        raise DomainError(422, "TOO_MANY_TAGS", f"An asset has at most {MAX_TAGS} tags.")
    return out


def update_asset(
    session: Session,
    asset_id: uuid.UUID,
    actor: Actor,
    *,
    name: str | None = None,
    tags: list[str] | None = None,
    favorite: bool | None = None,
) -> Asset:
    """Rename, tag (FR-049) or mark as favourite (FR-057). The slug, and so the export
    file name, never changes."""
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user can edit assets.")
    asset = get_asset(session, asset_id)
    changes: dict[str, Any] = {}
    if name is not None and name.strip() and name.strip() != asset.name:
        asset.name = changes["name"] = name.strip()[:200]
    if tags is not None:
        clean = normalise_tags(tags)
        if clean != list(asset.tags):
            asset.tags = clean
            changes["tags"] = clean
    if favorite is not None and favorite != (asset.favorite_at is not None):
        asset.favorite_at = utcnow() if favorite else None
        changes["favorite"] = favorite
    if changes:
        record(
            session,
            actor=actor,
            action="asset.updated",
            subject_type="asset",
            subject_id=asset.id,
            project_id=asset.project_id,
            data=changes,
        )
        session.flush()
    return asset


def tag_suggestions(
    session: Session, project_id: uuid.UUID, prefix: str = "", limit: int = 20
) -> list[tuple[str, int]]:
    """The project's tags starting with ``prefix``, most used first (auto-suggest)."""
    tag = func.unnest(Asset.tags).label("tag")
    inner = select(tag).where(Asset.project_id == project_id).subquery()
    q = (
        select(inner.c.tag, func.count().label("n"))
        .group_by(inner.c.tag)
        .order_by(func.count().desc(), inner.c.tag)
        .limit(limit)
    )
    clean = normalise_tags([prefix]) if prefix else []
    if clean:
        q = q.where(inner.c.tag.startswith(clean[0], autoescape=True))
    return [(t, n) for t, n in session.execute(q)]


@dataclass
class AssetRow:
    asset: Asset
    latest: AssetVersion | None
    version_count: int


def _has_version(query: Select[Asset], *conditions: Any) -> Select[Asset]:
    return query.where(exists().where(AssetVersion.asset_id == Asset.id, *conditions))


def list_assets(
    session: Session,
    *,
    project_id: uuid.UUID | None = None,
    category: str | None = None,
    state: str | None = None,
    q: str | None = None,
    style_id: uuid.UUID | None = None,
    character_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
    tag: str | None = None,
    favorite: bool | None = None,
    include_archived: bool = False,
    sort: str = "newest",
    before: uuid.UUID | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[AssetRow]:
    """Search and filter the library (FR-050).

    Newest first by default, with ``before`` as a cursor (an asset id, time-ordered UUIDv7);
    the other sorts page with ``offset``. Style and character match any version generated
    with them (the generation metadata, RULE-011).
    """
    order = {
        "newest": (Asset.id.desc(),),
        "oldest": (Asset.id.asc(),),
        "name": (func.lower(Asset.name).asc(), Asset.id.asc()),
        "updated": (Asset.updated_at.desc(), Asset.id.desc()),
    }.get(sort)
    if order is None:
        raise DomainError(422, "SORT_UNKNOWN", f"Sort by one of {', '.join(SORTS)}.")
    query = select(Asset).order_by(*order).limit(limit).offset(offset)
    if project_id:
        query = query.where(Asset.project_id == project_id)
    if category:
        query = query.where(Asset.category == category)
    if not include_archived:
        query = query.where(Asset.archived_at.is_(None))
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            Asset.name.ilike(pattern, escape="\\")
            | Asset.slug.ilike(pattern, escape="\\")
            | Asset.tags.contains([q.strip().lower()])
        )
    if state:
        query = _has_version(query, AssetVersion.state == state)
    if style_id:
        query = _has_version(
            query, AssetVersion.generation_metadata["style"]["id"].astext == str(style_id)
        )
    if character_id:
        query = _has_version(
            query,
            AssetVersion.generation_metadata["character"]["id"].astext == str(character_id),
        )
    if collection_id:
        query = query.where(
            exists().where(
                CollectionItem.asset_id == Asset.id, CollectionItem.collection_id == collection_id
            )
        )
    if tag:
        query = query.where(Asset.tags.contains([tag.strip().lower()]))
    if favorite is not None:
        query = query.where(
            Asset.favorite_at.is_not(None) if favorite else Asset.favorite_at.is_(None)
        )
    if before and sort == "newest":
        query = query.where(Asset.id < before)
    assets = list(session.scalars(query))
    versions: dict[uuid.UUID, list[AssetVersion]] = {a.id: [] for a in assets}
    if assets:
        for v in session.scalars(
            select(AssetVersion)
            .where(AssetVersion.asset_id.in_(versions.keys()))
            .order_by(AssetVersion.number.desc())
        ):
            versions[v.asset_id].append(v)
    rows = []
    for a in assets:
        live = [v for v in versions[a.id] if v.state != "deleted"]
        rows.append(AssetRow(asset=a, latest=live[0] if live else None, version_count=len(live)))
    return rows


# --- versions ---------------------------------------------------------------------------


def get_version(session: Session, version_id: uuid.UUID) -> AssetVersion:
    version = session.get(AssetVersion, version_id)
    if version is None:
        raise DomainError(404, "VERSION_NOT_FOUND", "Version not found.")
    return version


def list_versions(session: Session, asset_id: uuid.UUID) -> list[AssetVersion]:
    get_asset(session, asset_id)
    q = (
        select(AssetVersion)
        .where(AssetVersion.asset_id == asset_id)
        .order_by(AssetVersion.number.desc())
    )
    return list(session.scalars(q))


def list_versions_by_state(
    session: Session,
    *,
    project_id: uuid.UUID | None = None,
    state: str | None = None,
    include_archived_assets: bool = False,
    after: uuid.UUID | None = None,
    limit: int = 50,
) -> list[tuple[AssetVersion, Asset]]:
    """Versions across assets, oldest first: the review queue (FR-061) with
    ``state=awaiting_review``. ``after`` is a cursor (a version id)."""
    q = (
        select(AssetVersion, Asset)
        .join(Asset, Asset.id == AssetVersion.asset_id)
        .order_by(AssetVersion.id.asc())
        .limit(limit)
    )
    if project_id:
        q = q.where(Asset.project_id == project_id)
    if state:
        q = q.where(AssetVersion.state == state)
    if not include_archived_assets:
        q = q.where(Asset.archived_at.is_(None))
    if after:
        q = q.where(AssetVersion.id > after)
    return [(v, a) for v, a in session.execute(q)]


def history(session: Session, version_id: uuid.UUID) -> list[StateTransition]:
    get_version(session, version_id)
    q = (
        select(StateTransition)
        .where(StateTransition.asset_version_id == version_id)
        .order_by(StateTransition.id)
    )
    return list(session.scalars(q))


def add_version(
    session: Session,
    storage: LocalStorage,
    asset_id: uuid.UUID,
    stream: BinaryIO,
    *,
    mime: str,
    actor: Actor,
    width: int | None = None,
    height: int | None = None,
    generation_job_id: uuid.UUID | None = None,
    generation_metadata: dict[str, Any] | None = None,
) -> AssetVersion:
    """T-01: store a new immutable version in state ``generated`` (RULE-003)."""
    if actor not in ("user", "system"):
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Versions are added by the user or a job.")
    ext = MIME_EXT.get(mime)
    if ext is None:
        raise DomainError(415, "MEDIA_TYPE_UNSUPPORTED", "This file type is not supported.")
    # Lock the asset row so concurrent jobs cannot take the same version number.
    asset = session.scalar(
        select(Asset)
        .where(Asset.id == asset_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if asset is None:
        raise DomainError(404, "ASSET_NOT_FOUND", "Asset not found.")
    number = (
        session.scalar(
            select(func.max(AssetVersion.number)).where(AssetVersion.asset_id == asset_id)
        )
        or 0
    ) + 1
    key = f"{version_dir(asset.project_id, asset.id, number)}/original.{ext}"
    try:
        stored = storage.put(key, stream, max_bytes=MAX_VERSION_BYTES)
    except KeyExistsError as exc:  # a file without a row: never overwrite it
        raise DomainError(
            409, "VERSION_FILE_EXISTS", "A file for this version already exists."
        ) from exc
    version = AssetVersion(
        asset_id=asset.id,
        number=number,
        state="generated",
        storage_key=stored.key,
        sha256=stored.sha256,
        bytes=stored.bytes,
        mime=mime,
        width=width,
        height=height,
        generation_job_id=generation_job_id,
        generation_metadata=generation_metadata or {},
    )
    session.add(version)
    session.flush()
    session.add(
        StateTransition(
            asset_version_id=version.id,
            transition_id="T-01",
            from_state=None,
            to_state="generated",
            actor=actor,
        )
    )
    record(
        session,
        actor=actor,
        action="asset_version.generated",
        subject_type="asset_version",
        subject_id=version.id,
        project_id=asset.project_id,
        data={"asset_id": str(asset.id), "number": number, "sha256": stored.sha256},
    )
    return version


def transition(
    session: Session,
    version_id: uuid.UUID,
    action: str,
    actor: Actor,
    *,
    reason: str = "",
    data: dict[str, Any] | None = None,
) -> AssetVersion:
    """Run one lifecycle transition, checking state, actor and rule preconditions."""
    rule = TRANSITIONS.get(action)
    if rule is None or action == "delete":
        raise DomainError(422, "ACTION_UNKNOWN", f"Unknown action: {action}.")
    version = _lock_version(session, version_id)
    asset = get_asset(session, version.asset_id)
    project = get_project(session, asset.project_id)
    if not actor_allowed(rule.policy, actor, mcp_can_decide=project.mcp_can_decide):
        if actor == "mcp" and rule.policy == "decider":
            raise DomainError(
                403, "MCP_NOT_ALLOWED", "This project does not allow Claude to make decisions."
            )
        raise DomainError(403, "ACTOR_NOT_ALLOWED", f"The {actor} actor cannot {action}.")
    if version.state not in rule.sources:
        raise _not_allowed(version, action, f"Cannot {action} a version in state {version.state}.")
    reason = reason.strip()
    if rule.reason_required and not reason:
        raise DomainError(422, "REASON_REQUIRED", "A reason is required.")
    if action == "withdraw" and version.first_published_at is not None:  # RULE-020
        raise _not_allowed(
            version, action, "Approval cannot be withdrawn from a version that was published."
        )

    from_state = version.state
    if action == "archive":
        version.previous_state, version.state = from_state, "archived"
    elif action == "restore":
        version.state, version.previous_state = version.previous_state or "awaiting_review", None
    else:
        version.state = rule.target or from_state
    if version.state == "published" and version.first_published_at is None:
        version.first_published_at = utcnow()

    session.add(
        StateTransition(
            asset_version_id=version.id,
            transition_id=rule.id,
            from_state=from_state,
            to_state=version.state,
            actor=actor,
            reason=reason[:1000],
        )
    )
    record(
        session,
        actor=actor,
        action=f"asset_version.{action}",
        subject_type="asset_version",
        subject_id=version.id,
        project_id=asset.project_id,
        data={"from": from_state, "to": version.state, "transition": rule.id, "reason": reason}
        | (data or {}),
    )
    session.flush()
    return version


def delete_version(
    session: Session,
    storage: LocalStorage,
    version_id: uuid.UUID,
    actor: Actor,
    *,
    confirm: str,
) -> AssetVersion:
    """T-13: remove the files of a rejected or archived version; keep rows and audit."""
    rule = TRANSITIONS["delete"]
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user can permanently delete.")
    version = _lock_version(session, version_id)
    if confirm != str(version.id):
        raise DomainError(
            422, "CONFIRMATION_REQUIRED", "Confirm permanent deletion with the version id."
        )
    if version.state not in rule.sources:  # a published version must be archived first
        raise _not_allowed(
            version,
            "delete",
            f"Cannot delete a version in state {version.state}; archive or reject it first.",
        )
    asset = get_asset(session, version.asset_id)
    from_state, key = version.state, version.storage_key
    version.state, version.previous_state = "deleted", None
    version.storage_key, version.deleted_at = None, utcnow()
    session.add(
        StateTransition(
            asset_version_id=version.id,
            transition_id=rule.id,
            from_state=from_state,
            to_state="deleted",
            actor=actor,
        )
    )
    record(
        session,
        actor=actor,
        action="asset_version.deleted",
        subject_type="asset_version",
        subject_id=version.id,
        project_id=asset.project_id,
        data={"from": from_state, "sha256": version.sha256, "number": version.number},
    )
    session.flush()
    if key:
        storage.delete_prefix(key.rsplit("/", 1)[0])
    return version


@dataclass
class VersionFile:
    path: Path
    mime: str
    filename: str


def version_file(
    session: Session, storage: LocalStorage, version_id: uuid.UUID, size: str = "original"
) -> VersionFile:
    version = get_version(session, version_id)
    if version.storage_key is None:
        raise DomainError(410, "VERSION_DELETED", "The version file was permanently deleted.")
    asset = get_asset(session, version.asset_id)
    out = (version.processing or {}).get("output")
    if size == "original":
        key, mime = version.storage_key, version.mime
    elif size == "processed":
        if not out:
            raise DomainError(404, "FILE_NOT_AVAILABLE", "The version has not been processed.")
        key, mime = out["key"], out["mime"]
    elif size in DERIVED:
        key, mime = f"{version.storage_key.rsplit('/', 1)[0]}/{DERIVED[size]}", "image/webp"
    else:
        raise DomainError(422, "SIZE_UNKNOWN", "Unknown size.")
    try:
        path = storage.path(key)
    except FileNotFoundError as exc:
        raise DomainError(404, "FILE_NOT_AVAILABLE", "The file is not available.") from exc
    ext = key.rsplit(".", 1)[-1]
    suffix = "" if size == "original" else f"-{size}"
    return VersionFile(
        path=path, mime=mime, filename=f"{asset.slug}-v{version.number}{suffix}.{ext}"
    )


def consistency_report(session: Session, storage: LocalStorage) -> dict[str, list[str]]:
    """Versions whose file is missing, and version files no row points to."""
    rows: list[tuple[uuid.UUID, str]] = [
        (vid, key)
        for vid, key in session.execute(
            select(AssetVersion.id, AssetVersion.storage_key).where(
                AssetVersion.storage_key.is_not(None)
            )
        )
        if key is not None
    ]
    known_dirs = {key.rsplit("/", 1)[0] for _, key in rows}
    missing = [str(vid) for vid, key in rows if not storage.exists(key)]
    orphans = [
        key
        for key in storage.iter_keys("projects")
        if "/assets/" in key and key.rsplit("/", 1)[0] not in known_dirs
    ]
    return {"missing": missing, "orphans": orphans}
