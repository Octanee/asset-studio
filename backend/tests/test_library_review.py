"""Library and review (FR-049, FR-050, FR-051, FR-056, FR-057, FR-059, FR-061, FR-064)."""

import io
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from asset_studio.errors import DomainError
from asset_studio.modules.assets import service
from asset_studio.modules.assets.models import AssetVersion
from asset_studio.modules.processing import imaging
from asset_studio.modules.projects.config_schema import ProjectConfig
from asset_studio.modules.projects.service import create_project
from asset_studio.modules.review import service as review
from asset_studio.modules.storage.local import LocalStorage
from tests.conftest import MCP, ORIGIN, project_config

STYLE, CHARACTER = uuid.uuid4(), uuid.uuid4()


def _project(db: Session, name: str = "Exerzio illustrations") -> uuid.UUID:
    return create_project(db, ProjectConfig.model_validate(project_config(name=name)), "user").id


def _png(seed: int) -> bytes:
    out = io.BytesIO()
    image = Image.new("RGB", (64, 64), (255, 255, 255))
    image.paste((10 * seed % 255, 40, 160), (8 + seed, 8, 40 + seed, 56))
    image.save(out, "PNG")
    return out.getvalue()


def _version(
    db: Session,
    storage: LocalStorage,
    pid: uuid.UUID,
    name: str,
    *,
    data: bytes | None = None,
    metadata: dict[str, Any] | None = None,
) -> AssetVersion:
    asset = service.create_asset(db, pid, category="lower-body", name=name, actor="system")
    return service.add_version(
        db,
        storage,
        asset.id,
        io.BytesIO(data or _png(len(name))),
        mime="image/png",
        actor="system",
        generation_metadata=metadata,
    )


def _to_review(db: Session, version: AssetVersion, *, dhash: str | None = None) -> None:
    service.transition(db, version.id, "start_processing", "system")
    if dhash:
        version.processing = {"dhash": dhash}
    service.transition(db, version.id, "processing_succeeded", "system")


def _names(r: Any) -> list[str]:
    assert r.status_code == 200, r.text
    return [a["name"] for a in r.json()]


# --- tags and favourites --------------------------------------------------------------------


def test_fr049_tags_are_normalised_and_suggested(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    squat = _version(db, storage, pid, "Squat").asset_id
    lunge = _version(db, storage, pid, "Lunge").asset_id
    r = client.patch(
        f"/api/v1/assets/{squat}", json={"tags": [" Legs ", "Front View", "legs"]}, headers=ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ["legs", "front-view"]
    client.patch(f"/api/v1/assets/{lunge}", json={"tags": ["legs", "lunge"]}, headers=ORIGIN)

    r = client.get("/api/v1/assets/tags", params={"project_id": str(pid)})
    assert r.json()[0] == {"tag": "legs", "count": 2}
    r = client.get("/api/v1/assets/tags", params={"project_id": str(pid), "prefix": "LU"})
    assert [t["tag"] for t in r.json()] == ["lunge"]
    r = client.get("/api/v1/assets", params={"project_id": str(pid), "tag": "lunge"})
    assert _names(r) == ["Lunge"]
    r = client.get("/api/v1/assets", params={"project_id": str(pid), "q": "front-view"})
    assert _names(r) == ["Squat"]

    too_many = {"tags": [f"t{i}" for i in range(21)]}
    r = client.patch(f"/api/v1/assets/{squat}", json=too_many, headers=ORIGIN)
    assert r.json()["code"] == "TOO_MANY_TAGS"
    r = client.patch(f"/api/v1/assets/{squat}", json={"tags": []}, headers=MCP)
    assert r.json()["code"] == "ACTOR_NOT_ALLOWED"


def test_fr057_favourites_filter_and_audit(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    squat = _version(db, storage, pid, "Squat").asset_id
    _version(db, storage, pid, "Plank")
    r = client.patch(f"/api/v1/assets/{squat}", json={"favorite": True}, headers=ORIGIN)
    assert r.json()["favorite_at"] is not None
    params = {"project_id": str(pid), "favorite": "true"}
    assert _names(client.get("/api/v1/assets", params=params)) == ["Squat"]
    params["favorite"] = "false"
    assert _names(client.get("/api/v1/assets", params=params)) == ["Plank"]
    trail = client.get("/api/v1/audit", params={"subject_id": str(squat)}).json()
    assert trail[0]["action"] == "asset.updated"
    assert trail[0]["data"] == {"favorite": True}


# --- collections ----------------------------------------------------------------------------


def test_fr056_collections_group_assets_without_changing_them(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    squat = _version(db, storage, pid, "Squat").asset_id
    plank = _version(db, storage, pid, "Plank").asset_id
    r = client.post(f"/api/v1/projects/{pid}/collections", json={"name": "Week 1"}, headers=ORIGIN)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/collections", json={"name": "week 1"}, headers=ORIGIN)
    assert r.json()["code"] == "COLLECTION_EXISTS"

    body = {"asset_ids": [str(squat), str(plank), str(squat)]}
    r = client.post(f"/api/v1/collections/{cid}/assets", json=body, headers=ORIGIN)
    assert r.json()["asset_count"] == 2
    r = client.post(f"/api/v1/collections/{cid}/assets", json=body, headers=ORIGIN)
    assert r.json()["asset_count"] == 2  # adding again is a no-op

    other = _version(db, storage, _project(db, "Other"), "Other").asset_id
    r = client.post(
        f"/api/v1/collections/{cid}/assets", json={"asset_ids": [str(other)]}, headers=ORIGIN
    )
    assert r.json()["code"] == "ASSET_OTHER_PROJECT"

    params = {"project_id": str(pid), "collection_id": cid, "sort": "name"}
    assert _names(client.get("/api/v1/assets", params=params)) == ["Plank", "Squat"]
    assert client.get(f"/api/v1/assets/{squat}").json()["collection_ids"] == [cid]

    r = client.delete(f"/api/v1/collections/{cid}/assets/{plank}", headers=ORIGIN)
    assert r.json()["asset_count"] == 1
    r = client.patch(f"/api/v1/collections/{cid}", json={"name": "Legs"}, headers=ORIGIN)
    assert r.json()["name"] == "Legs"
    r = client.post(f"/api/v1/projects/{pid}/collections", json={"name": "x"}, headers=MCP)
    assert r.json()["code"] == "ACTOR_NOT_ALLOWED"

    assert client.delete(f"/api/v1/collections/{cid}", headers=ORIGIN).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}/collections").json() == []
    assert client.get(f"/api/v1/assets/{squat}").json()["collection_ids"] == []
    trail = client.get("/api/v1/audit", params={"subject_id": cid}).json()
    actions = [e["action"] for e in trail]
    assert actions[0] == "collection.deleted"
    assert "collection.assets_added" in actions


# --- library filters ------------------------------------------------------------------------


def test_fr050_filters_by_style_character_state_and_sorts(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    styled = {"style": {"id": str(STYLE), "version": 1}, "character": None}
    both = {"style": {"id": str(STYLE), "version": 2}, "character": {"id": str(CHARACTER)}}
    _version(db, storage, pid, "Bridge", metadata=styled)
    lunge = _version(db, storage, pid, "Lunge", metadata=both)
    _version(db, storage, pid, "Ab wheel")
    _to_review(db, lunge)

    def names(**params: Any) -> list[str]:
        return _names(client.get("/api/v1/assets", params={"project_id": str(pid), **params}))

    assert names(style_id=str(STYLE), sort="name") == ["Bridge", "Lunge"]
    assert names(character_id=str(CHARACTER)) == ["Lunge"]
    assert names(state="awaiting_review") == ["Lunge"]
    assert names(sort="name") == ["Ab wheel", "Bridge", "Lunge"]
    assert names(sort="name", offset=1, limit=1) == ["Bridge"]
    assert names(sort="oldest")[0] == "Bridge"
    assert client.get("/api/v1/assets", params={"sort": "size"}).status_code == 422


def test_fr051_asset_trail_lists_asset_and_version_entries(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    v = _version(db, storage, pid, "Squat")
    _to_review(db, v)
    params = [("subject_id", str(v.asset_id)), ("subject_id", str(v.id))]
    actions = [e["action"] for e in client.get("/api/v1/audit", params=params).json()]
    assert actions == [
        "asset_version.processing_succeeded",
        "asset_version.start_processing",
        "asset_version.generated",
        "asset.created",
    ]


# --- review queue and comments --------------------------------------------------------------


def test_fr061_review_queue_is_oldest_first_across_assets(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    first = _version(db, storage, pid, "Squat")
    second = _version(db, storage, pid, "Lunge")
    _version(db, storage, pid, "Plank")  # still generated
    for v in (first, second):
        _to_review(db, v)
    params = {"project_id": str(pid), "state": "awaiting_review"}
    rows = client.get("/api/v1/versions", params=params).json()
    assert [(r["id"], r["asset"]["name"]) for r in rows] == [
        (str(first.id), "Squat"),
        (str(second.id), "Lunge"),
    ]
    rest = client.get("/api/v1/versions", params=params | {"after": str(first.id)}).json()
    assert [r["id"] for r in rest] == [str(second.id)]


def test_fr064_user_and_claude_comment_and_comments_are_kept(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    v = _version(db, storage, pid, "Squat")
    _to_review(db, v)
    url = f"/api/v1/versions/{v.id}/comments"
    r = client.post(url, json={"body": "  Knees look fine.  "}, headers=ORIGIN)
    assert r.status_code == 201, r.text
    # Claude may comment even though the project does not let it decide (RULE-005).
    r = client.post(url, json={"body": "The left hand has six fingers."}, headers=MCP)
    assert r.status_code == 201, r.text
    r = client.post(f"/api/v1/versions/{v.id}/transitions", json={"action": "approve"}, headers=MCP)
    assert r.json()["code"] == "MCP_NOT_ALLOWED"

    comments = client.get(url).json()
    assert [(c["actor"], c["body"]) for c in comments] == [
        ("user", "Knees look fine."),
        ("mcp", "The left hand has six fingers."),
    ]
    assert client.post(url, json={"body": "   "}, headers=ORIGIN).json()["code"] == "COMMENT_EMPTY"
    assert client.post(url, json={"body": "x" * 4001}, headers=ORIGIN).status_code == 422
    trail = client.get("/api/v1/audit", params={"action": "review_comment.created"}).json()
    assert {e["actor"] for e in trail} == {"user", "mcp"}

    with pytest.raises(DBAPIError), db.begin_nested():
        db.execute(text("UPDATE review_comment SET body = 'changed'"))


def test_comment_needs_a_live_version_and_a_person(db: Session, storage: LocalStorage) -> None:
    v = _version(db, storage, _project(db), "Squat")
    with pytest.raises(DomainError) as err:
        review.add_comment(db, v.id, "hello", "system")
    assert err.value.code == "ACTOR_NOT_ALLOWED"
    v.state = "deleted"
    with pytest.raises(DomainError) as err:
        review.add_comment(db, v.id, "too late", "user")
    assert err.value.code == "VERSION_DELETED"


# --- duplicates -----------------------------------------------------------------------------


def _encode(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_fr059_dhash_ignores_transparency_and_tracks_similarity() -> None:
    base = Image.new("RGB", (128, 128), (255, 255, 255))
    base.paste((20, 40, 160), (32, 16, 96, 112))
    cut = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    cut.paste((20, 40, 160, 255), (32, 16, 96, 112))
    moved = Image.new("RGB", (128, 128), (255, 255, 255))
    moved.paste((20, 40, 160), (8, 60, 120, 100))

    h = imaging.dhash(_encode(base))
    assert len(h) == 16
    assert imaging.dhash(_encode(cut)) == h
    assert review._distance(h, imaging.dhash(_encode(moved))) > review.NEAR_DUPLICATE


def test_fr059_duplicates_lists_exact_and_near_copies(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    data = _png(3)
    v = _version(db, storage, pid, "Squat", data=data)
    _version(db, storage, pid, "Squat copy", data=data)
    near = _version(db, storage, pid, "Squat again")
    far = _version(db, storage, pid, "Plank")
    elsewhere = _version(db, storage, _project(db, "Other"), "Squat", data=data)
    _to_review(db, v, dhash="ffff0000ffff0000")
    _to_review(db, near, dhash="ffff0000ffff0003")  # 2 bits apart
    _to_review(db, far, dhash="0000ffff0000ffff")
    _to_review(db, elsewhere, dhash="ffff0000ffff0000")  # another project: not listed

    rows = client.get(f"/api/v1/versions/{v.id}/duplicates").json()
    assert [(r["asset"]["name"], r["exact"], r["distance"]) for r in rows] == [
        ("Squat copy", True, 0),
        ("Squat again", False, 2),
    ]
