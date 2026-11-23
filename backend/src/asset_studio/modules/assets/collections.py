"""Collections (FR-056): named groups of a project's assets, kept by the user.

A collection only points at assets; removing one, or an asset from it, never changes the
assets or their versions. Every change is audited (RULE-006).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from asset_studio.errors import DomainError
from asset_studio.modules.assets.models import Asset, Collection, CollectionItem
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.projects.service import get_project


@dataclass
class CollectionRow:
    collection: Collection
    asset_count: int


def _user(actor: Actor) -> None:
    if actor != "user":
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Only the user can change collections.")


def _clean(name: str) -> str:
    name = " ".join(name.split())[:120]
    if not name:
        raise DomainError(422, "NAME_REQUIRED", "A collection needs a name.")
    return name


def get_collection(session: Session, collection_id: uuid.UUID) -> Collection:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise DomainError(404, "COLLECTION_NOT_FOUND", "Collection not found.")
    return collection


def _count(session: Session, collection_id: uuid.UUID) -> int:
    return int(
        session.scalar(select(func.count()).where(CollectionItem.collection_id == collection_id))
        or 0
    )


def row(session: Session, collection: Collection) -> CollectionRow:
    return CollectionRow(collection, _count(session, collection.id))


def list_collections(session: Session, project_id: uuid.UUID) -> list[CollectionRow]:
    get_project(session, project_id)
    counts = (
        select(CollectionItem.collection_id, func.count().label("n"))
        .group_by(CollectionItem.collection_id)
        .subquery()
    )
    q = (
        select(Collection, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.collection_id == Collection.id)
        .where(Collection.project_id == project_id)
        .order_by(func.lower(Collection.name))
    )
    return [CollectionRow(c, int(n)) for c, n in session.execute(q)]


def _unique_name(session: Session, project_id: uuid.UUID, name: str, own: uuid.UUID | None) -> None:
    clash = session.scalar(
        select(Collection.id).where(
            Collection.project_id == project_id, func.lower(Collection.name) == name.lower()
        )
    )
    if clash is not None and clash != own:
        raise DomainError(409, "COLLECTION_EXISTS", "A collection with this name exists.")


def create_collection(
    session: Session, project_id: uuid.UUID, name: str, actor: Actor
) -> Collection:
    _user(actor)
    get_project(session, project_id)
    name = _clean(name)
    _unique_name(session, project_id, name, None)
    collection = Collection(project_id=project_id, name=name)
    session.add(collection)
    session.flush()
    record(
        session,
        actor=actor,
        action="collection.created",
        subject_type="collection",
        subject_id=collection.id,
        project_id=project_id,
        data={"name": name},
    )
    return collection


def rename_collection(
    session: Session, collection_id: uuid.UUID, name: str, actor: Actor
) -> Collection:
    _user(actor)
    collection = get_collection(session, collection_id)
    name = _clean(name)
    if name != collection.name:
        _unique_name(session, collection.project_id, name, collection.id)
        record(
            session,
            actor=actor,
            action="collection.renamed",
            subject_type="collection",
            subject_id=collection.id,
            project_id=collection.project_id,
            data={"from": collection.name, "to": name},
        )
        collection.name = name
        session.flush()
    return collection


def delete_collection(session: Session, collection_id: uuid.UUID, actor: Actor) -> None:
    """Remove the group; its assets stay as they are."""
    _user(actor)
    collection = get_collection(session, collection_id)
    record(
        session,
        actor=actor,
        action="collection.deleted",
        subject_type="collection",
        subject_id=collection.id,
        project_id=collection.project_id,
        data={"name": collection.name, "assets": _count(session, collection.id)},
    )
    session.delete(collection)
    session.flush()


def add_assets(
    session: Session, collection_id: uuid.UUID, asset_ids: list[uuid.UUID], actor: Actor
) -> CollectionRow:
    _user(actor)
    collection = get_collection(session, collection_id)
    wanted = list(dict.fromkeys(asset_ids))
    found = {a.id: a for a in session.scalars(select(Asset).where(Asset.id.in_(wanted)))}
    missing = [str(i) for i in wanted if i not in found]
    if missing:
        raise DomainError(404, "ASSET_NOT_FOUND", "Asset not found.", {"asset_ids": missing})
    if any(a.project_id != collection.project_id for a in found.values()):
        raise DomainError(
            422, "ASSET_OTHER_PROJECT", "A collection holds assets of its own project only."
        )
    present = set(
        session.scalars(
            select(CollectionItem.asset_id).where(
                CollectionItem.collection_id == collection.id,
                CollectionItem.asset_id.in_(wanted),
            )
        )
    )
    added = [i for i in wanted if i not in present]
    for asset_id in added:
        session.add(CollectionItem(collection_id=collection.id, asset_id=asset_id))
    try:
        session.flush()
    except IntegrityError as exc:  # a concurrent add of the same asset
        raise DomainError(409, "COLLECTION_CHANGED", "The collection changed; try again.") from exc
    if added:
        record(
            session,
            actor=actor,
            action="collection.assets_added",
            subject_type="collection",
            subject_id=collection.id,
            project_id=collection.project_id,
            data={"asset_ids": [str(i) for i in added]},
        )
    return row(session, collection)


def remove_asset(
    session: Session, collection_id: uuid.UUID, asset_id: uuid.UUID, actor: Actor
) -> CollectionRow:
    _user(actor)
    collection = get_collection(session, collection_id)
    item = session.get(CollectionItem, (collection.id, asset_id))
    if item is not None:
        session.delete(item)
        session.flush()
        record(
            session,
            actor=actor,
            action="collection.asset_removed",
            subject_type="collection",
            subject_id=collection.id,
            project_id=collection.project_id,
            data={"asset_id": str(asset_id)},
        )
    return row(session, collection)


def collections_of(
    session: Session, asset_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    out: dict[uuid.UUID, list[uuid.UUID]] = {i: [] for i in asset_ids}
    if asset_ids:
        for asset_id, collection_id in session.execute(
            select(CollectionItem.asset_id, CollectionItem.collection_id).where(
                CollectionItem.asset_id.in_(asset_ids)
            )
        ):
            out[asset_id].append(collection_id)
    return out
