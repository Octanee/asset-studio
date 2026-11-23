"""Review comments (FR-061, FR-064) and duplicate detection (FR-059).

Comments come from the user or from Claude over MCP; MCP may always comment, deciding is a
lifecycle transition governed by RULE-005. Comments are append-only (a trigger enforces it)
and every one is audited (RULE-006).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from asset_studio.errors import DomainError
from asset_studio.modules.assets import service as assets
from asset_studio.modules.assets.models import Asset, AssetVersion
from asset_studio.modules.audit.service import Actor, record
from asset_studio.modules.review.models import COMMENT_ACTORS, MAX_COMMENT, ReviewComment

# Hamming distance (of 64 bits) up to which two images count as near-duplicates.
NEAR_DUPLICATE = 6
MAX_DUPLICATES = 12


def list_comments(session: Session, version_id: uuid.UUID) -> list[ReviewComment]:
    assets.get_version(session, version_id)
    q = (
        select(ReviewComment)
        .where(ReviewComment.asset_version_id == version_id)
        .order_by(ReviewComment.id)
    )
    return list(session.scalars(q))


def add_comment(session: Session, version_id: uuid.UUID, body: str, actor: Actor) -> ReviewComment:
    if actor not in COMMENT_ACTORS:
        raise DomainError(403, "ACTOR_NOT_ALLOWED", "Comments come from the user or Claude.")
    body = body.strip()
    if not body:
        raise DomainError(422, "COMMENT_EMPTY", "The comment is empty.")
    if len(body) > MAX_COMMENT:
        raise DomainError(
            422, "COMMENT_TOO_LONG", f"A comment has at most {MAX_COMMENT} characters."
        )
    version = assets.get_version(session, version_id)
    if version.state == "deleted":
        raise DomainError(410, "VERSION_DELETED", "The version was permanently deleted.")
    asset = assets.get_asset(session, version.asset_id)
    comment = ReviewComment(asset_version_id=version.id, actor=actor, body=body)
    session.add(comment)
    session.flush()
    record(
        session,
        actor=actor,
        action="review_comment.created",
        subject_type="asset_version",
        subject_id=version.id,
        project_id=asset.project_id,
        data={"comment_id": str(comment.id), "length": len(body)},
    )
    return comment


@dataclass
class Duplicate:
    version: AssetVersion
    asset: Asset
    distance: int
    exact: bool


def _distance(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def duplicates(session: Session, version_id: uuid.UUID) -> list[Duplicate]:
    """Other versions of the project with the same file or a near-identical image.

    Exact: the same original or processed file (SHA-256). Near: the difference hash of the
    processed image is at most ``NEAR_DUPLICATE`` bits apart. Informative only.
    """
    version = assets.get_version(session, version_id)
    asset = assets.get_asset(session, version.asset_id)
    mine = version.processing or {}
    my_hash = mine.get("dhash")
    my_files = {version.sha256, (mine.get("output") or {}).get("sha256")} - {None}
    rows = session.execute(
        select(AssetVersion, Asset)
        .join(Asset, Asset.id == AssetVersion.asset_id)
        .where(
            Asset.project_id == asset.project_id,
            AssetVersion.id != version.id,
            AssetVersion.state != "deleted",
        )
    )
    found: list[Duplicate] = []
    for other, other_asset in rows:
        theirs = other.processing or {}
        files = {other.sha256, (theirs.get("output") or {}).get("sha256")} - {None}
        exact = bool(my_files & files)
        distance = _distance(my_hash, theirs["dhash"]) if my_hash and theirs.get("dhash") else 64
        if exact or distance <= NEAR_DUPLICATE:
            found.append(Duplicate(other, other_asset, 0 if exact else distance, exact))
    found.sort(key=lambda d: (d.distance, d.version.id))
    return found[:MAX_DUPLICATES]
