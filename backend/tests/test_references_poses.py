"""References and poses (FR-020 to FR-022, FR-025, FR-026, AC-011)."""

import struct
import uuid
from collections.abc import Iterator
from dataclasses import astuple
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.poses import detection
from asset_studio.modules.poses import service as poses
from asset_studio.modules.poses.builtin import BUILTIN_POSES
from asset_studio.modules.poses.detection import Box, Detection
from asset_studio.modules.poses.skeleton import KEYPOINTS, mirror
from asset_studio.modules.providers.png import sample_image
from asset_studio.modules.references.imaging import ImageError, sniff
from asset_studio.modules.storage.local import LocalStorage
from tests.conftest import MCP, ORIGIN, project_config
from tests.test_jobs import _runner

PNG = sample_image(96, 128, seed=1)


def _project(client: TestClient) -> str:
    r = client.post("/api/v1/projects", json=project_config(), headers=ORIGIN)
    return str(r.json()["id"])


def _upload(
    client: TestClient, pid: str, data: bytes = PNG, role: str = "style", **params: str
) -> Any:
    return client.post(
        f"/api/v1/projects/{pid}/references",
        params={"role": role, **params},
        content=data,
        headers={**ORIGIN, "Content-Type": "image/png"},
    )


# --- file checks ---------------------------------------------------------------------------


def _jpeg(width: int, height: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof = b"\xff\xc0" + struct.pack(">HBHH", 17, 8, height, width) + b"\x00" * 10
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def _webp(width: int, height: int) -> bytes:
    body = b"VP8X" + struct.pack("<I", 10) + b"\x00" * 4
    body += (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


def test_sniff_reads_type_and_size_from_the_bytes() -> None:
    assert astuple(sniff(PNG)) == ("image/png", "png", 96, 128)
    assert astuple(sniff(_jpeg(640, 480))) == ("image/jpeg", "jpg", 640, 480)
    assert astuple(sniff(_webp(300, 200))) == ("image/webp", "webp", 300, 200)
    for bad in (b"GIF89a....", b"<svg xmlns='http://www.w3.org/2000/svg'/>", PNG[:20]):
        with pytest.raises(ImageError):
            sniff(bad)


# --- references ----------------------------------------------------------------------------


def test_fr025_upload_validates_the_file_and_keeps_the_role(
    client: TestClient, storage: LocalStorage
) -> None:
    pid = _project(client)
    r = _upload(client, pid, name="C:\\photos\\ola front.png")
    assert r.status_code == 201, r.text
    ref = r.json()
    assert (ref["role"], ref["name"], ref["width"], ref["height"]) == (
        "style",
        "ola front.png",
        96,
        128,
    )
    key = f"projects/{pid}/references/{ref['id']}.png"
    assert storage.exists(key)
    file = client.get(f"/api/v1/references/{ref['id']}/file")
    assert (file.status_code, file.content) == (200, PNG)
    assert file.headers["x-content-type-options"] == "nosniff"


def test_fr025_rejected_files(client: TestClient) -> None:
    pid = _project(client)
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>"
    assert _upload(client, pid, svg).json()["code"] == "MEDIA_TYPE_UNSUPPORTED"
    tiny = _upload(client, pid, sample_image(32, 32, seed=2))
    assert tiny.json()["code"] == "IMAGE_SIZE_OUT_OF_RANGE"
    assert _upload(client, pid, b"").json()["code"] == "FILE_EMPTY"
    assert _upload(client, pid, role="selfie").status_code == 422
    _upload(client, pid)
    dup = _upload(client, pid)
    assert (dup.status_code, dup.json()["code"]) == (409, "REFERENCE_DUPLICATE")


def test_change_role_filter_and_archive(client: TestClient) -> None:
    pid = _project(client)
    rid = _upload(client, pid).json()["id"]
    r = client.patch(f"/api/v1/references/{rid}", json={"role": "pose"}, headers=ORIGIN)
    assert r.json()["role"] == "pose"
    assert len(client.get(f"/api/v1/projects/{pid}/references?role=pose").json()) == 1
    assert client.get(f"/api/v1/projects/{pid}/references?role=style").json() == []
    client.post(f"/api/v1/references/{rid}/archive", headers=ORIGIN)
    assert client.get(f"/api/v1/projects/{pid}/references").json() == []
    # The file stays: past jobs and versions may still point at it (FR-026).
    assert client.get(f"/api/v1/references/{rid}/file").status_code == 200


def test_fr026_links_to_styles_and_characters(client: TestClient) -> None:
    pid = _project(client)
    rid = _upload(client, pid).json()["id"]
    sid = client.post(
        f"/api/v1/projects/{pid}/styles", json={"name": "Flat"}, headers=ORIGIN
    ).json()["id"]
    link = client.put(
        f"/api/v1/references/{rid}/links/style/{sid}", json={"weight": 0.6}, headers=ORIGIN
    )
    assert link.status_code == 200 and link.json()["weight"] == 0.6
    linked = client.get(
        f"/api/v1/projects/{pid}/references", params={"target_type": "style", "target_id": sid}
    ).json()
    assert [r["id"] for r in linked] == [rid]
    assert len(client.get(f"/api/v1/references/{rid}/links").json()) == 1
    gone = client.delete(f"/api/v1/references/{rid}/links/style/{sid}", headers=ORIGIN)
    assert gone.status_code == 204
    assert client.get(f"/api/v1/references/{rid}/links").json() == []


def test_links_stay_inside_the_project(client: TestClient) -> None:
    rid = _upload(client, _project(client)).json()["id"]
    other = client.post(
        "/api/v1/projects", json=project_config(name="Other"), headers=ORIGIN
    ).json()["id"]
    sid = client.post(
        f"/api/v1/projects/{other}/styles", json={"name": "Flat"}, headers=ORIGIN
    ).json()["id"]
    r = client.put(f"/api/v1/references/{rid}/links/style/{sid}", json={}, headers=ORIGIN)
    assert r.json()["code"] == "LINK_OTHER_PROJECT"
    r = client.put(f"/api/v1/references/{rid}/links/job/{uuid.uuid4()}", json={}, headers=ORIGIN)
    assert r.status_code == 422


# --- poses ---------------------------------------------------------------------------------


def _points(value: float = 0.5) -> list[list[float] | None]:
    return [[value, 0.1 + i * 0.04, 1.0] if i < 6 else None for i in range(len(KEYPOINTS))]


def test_fr020_library_lists_builtin_then_project_poses(client: TestClient) -> None:
    pid = _project(client)
    builtin = client.get("/api/v1/poses").json()
    assert [p["name"] for p in builtin] == sorted(p.name for p in BUILTIN_POSES)
    assert all(p["source"] == "library" and p["project_id"] is None for p in builtin)
    r = client.post(
        f"/api/v1/projects/{pid}/poses",
        json={"name": "A lunge", "view": "left", "keypoints": _points()},
        headers=ORIGIN,
    )
    assert r.status_code == 201, r.text
    listed = client.get(f"/api/v1/poses?project_id={pid}").json()
    assert listed[-1]["name"] == "A lunge" and listed[-1]["source"] == "editor"
    assert len(listed) == len(BUILTIN_POSES) + 1


def test_fr021_editor_saves_and_validates(client: TestClient) -> None:
    pid = _project(client)
    few = _points()
    few[3:6] = [None, None, None]
    r = client.post(
        f"/api/v1/projects/{pid}/poses", json={"name": "x", "keypoints": few}, headers=ORIGIN
    )
    assert r.json()["code"] == "POSE_TOO_FEW_JOINTS"
    out_of_canvas = _points(1.5)
    r = client.post(
        f"/api/v1/projects/{pid}/poses",
        json={"name": "x", "keypoints": out_of_canvas},
        headers=ORIGIN,
    )
    assert r.status_code == 422
    pose = client.post(
        f"/api/v1/projects/{pid}/poses", json={"name": "x", "keypoints": _points()}, headers=ORIGIN
    ).json()
    moved = client.patch(
        f"/api/v1/poses/{pose['id']}", json={"keypoints": _points(0.4)}, headers=ORIGIN
    )
    assert moved.json()["keypoints"][0] == [0.4, 0.1, 1.0]


def test_builtin_poses_are_read_only(client: TestClient) -> None:
    pose_id = BUILTIN_POSES[0].id
    r = client.patch(f"/api/v1/poses/{pose_id}", json={"name": "Mine"}, headers=ORIGIN)
    assert r.json()["code"] == "POSE_BUILTIN_READONLY"
    assert client.post(f"/api/v1/poses/{pose_id}/archive", headers=ORIGIN).status_code == 409


def test_mirror_swaps_sides() -> None:
    standing = BUILTIN_POSES[0].keypoints
    flipped = mirror(standing)
    right_wrist, left_wrist = KEYPOINTS.index("right_wrist"), KEYPOINTS.index("left_wrist")
    assert flipped[left_wrist] == (
        round(1 - standing[right_wrist][0], 4),
        *standing[right_wrist][1:],
    )  # type: ignore[index]
    assert mirror(flipped) == [
        None if p is None else (round(p[0], 4), p[1], p[2]) for p in standing
    ]


class FakeDetector:
    name = "fake"

    def __init__(self, found: bool = True) -> None:
        self.found = found
        self.calls: list[Box | None] = []

    def detect(self, image: bytes, box: Box | None = None) -> Detection | None:
        assert image == PNG
        self.calls.append(box)
        if not self.found:
            return None
        points = BUILTIN_POSES[0].keypoints
        return Detection(keypoints=points, score=0.82, box=box or (0.1, 0.05, 0.9, 0.95))


@pytest.fixture
def detector(monkeypatch: pytest.MonkeyPatch, storage: LocalStorage) -> Iterator[FakeDetector]:
    fake = FakeDetector()
    monkeypatch.setattr(poses, "get_storage", lambda: storage)
    detection.set_detector(fake)
    yield fake
    detection.set_detector(None)


def _detect(client: TestClient, connection: Connection, rid: str, **body: Any) -> Any:
    r = client.post("/api/v1/poses:detect", json={"reference_id": rid, **body}, headers=ORIGIN)
    assert r.status_code == 202, r.text
    assert (r.json()["kind"], r.json()["lane"]) == ("detect_pose", "cpu")
    _runner(connection, {"detect_pose": poses.handle_detect_pose}).tick()
    return client.get(f"/api/v1/jobs/{r.json()['id']}").json()


def test_ac011_detect_edit_and_save(
    client: TestClient, connection: Connection, detector: FakeDetector
) -> None:
    pid = _project(client)
    rid = _upload(client, pid, role="pose").json()["id"]
    job = _detect(client, connection, rid)
    assert job["state"] == "completed", job
    result = job["result"]
    assert (result["detector"], result["score"], result["aspect"]) == ("fake", 0.82, 0.75)
    edited = result["keypoints"]
    edited[0] = [0.52, 0.15, 1.0]  # the user drags the nose
    saved = client.post(
        f"/api/v1/projects/{pid}/poses",
        json={
            "name": "From photo",
            "aspect": result["aspect"],
            "keypoints": edited,
            "source_reference_id": rid,
        },
        headers=ORIGIN,
    ).json()
    assert (saved["source"], saved["source_reference_id"]) == ("detected", rid)
    assert saved["keypoints"][0] == [0.52, 0.15, 1.0]


def test_drawn_box_skips_the_person_detector(
    client: TestClient, connection: Connection, detector: FakeDetector
) -> None:
    rid = _upload(client, _project(client)).json()["id"]
    job = _detect(client, connection, rid, box=[0.2, 0.1, 0.8, 0.9])
    assert detector.calls == [(0.2, 0.1, 0.8, 0.9)]
    assert job["result"]["box"] == [0.2, 0.1, 0.8, 0.9]
    bad = client.post(
        "/api/v1/poses:detect",
        json={"reference_id": rid, "box": [0.8, 0.1, 0.2, 0.9]},
        headers=ORIGIN,
    )
    assert bad.json()["code"] == "POSE_BOX_INVALID"


def test_no_person_found(
    client: TestClient, connection: Connection, detector: FakeDetector
) -> None:
    detector.found = False
    job = _detect(client, connection, _upload(client, _project(client)).json()["id"])
    assert (job["state"], job["error"]["code"]) == ("failed", "POSE_NOT_FOUND")


def test_without_a_detector_the_job_says_so(
    client: TestClient, connection: Connection, db: Session
) -> None:
    detection.set_detector(None)
    job = _detect(client, connection, _upload(client, _project(client)).json()["id"])
    assert (job["state"], job["error"]["code"]) == ("failed", "POSE_DETECTOR_NOT_INSTALLED")
    assert jobs.get_job(db, uuid.UUID(job["id"])).attempts == 1


def test_claude_can_detect_but_only_with_a_session_or_token(
    client: TestClient, anon: TestClient
) -> None:
    rid = _upload(client, _project(client)).json()["id"]
    r = client.post("/api/v1/poses:detect", json={"reference_id": rid}, headers=MCP)
    assert r.status_code == 202
    assert anon.get("/api/v1/poses").status_code == 401
