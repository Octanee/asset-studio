"""DWPose detector and model installer (ADR-009, FR-022).

The real models (~350 MB) are not in CI. ``test_real_models_find_a_person`` runs when
ASSET_STUDIO_TEST_POSE_MODELS (a folder with the two .onnx files) and
ASSET_STUDIO_TEST_POSE_IMAGE (an image with one person) are set.
"""

import hashlib
import os
from pathlib import Path

import httpx
import numpy as np
import pytest

from asset_studio.modules.poses import dwpose, install
from asset_studio.modules.poses.detection import load_default_detector
from asset_studio.modules.poses.skeleton import KEYPOINTS


def test_letterbox_keeps_the_aspect_and_pads_grey() -> None:
    rgb = np.zeros((100, 200, 3), dtype=np.uint8)
    pad, ratio = dwpose.letterbox(rgb, size=64)
    assert pad.shape == (64, 64, 3) and ratio == pytest.approx(0.32)
    assert pad[0, 0, 0] == 0 and pad[63, 0, 0] == 114  # image on top, padding below


def test_decode_yolox_picks_the_person_box() -> None:
    size = 64
    rows = sum((size // s) ** 2 for s in (8, 16, 32))
    out = np.zeros((rows, 85), dtype=np.float32)
    # Row 9 is grid cell (1, 1) at stride 8: centre (8 + 8, 8 + 8) = (16, 16) after the offset.
    out[9, :4] = [1.0, 1.0, np.log(2.0), np.log(4.0)]  # centre (16, 16), size 16 x 32
    out[9, 4:6] = [0.9, 0.8]
    boxes, scores = dwpose.decode_yolox(out, ratio=0.5, size=size)
    best = int(np.argmax(scores))
    assert best == 9 and scores[best] == pytest.approx(0.72)
    assert boxes[best].tolist() == pytest.approx([16, 0, 48, 64])  # scaled back by 1 / 0.5


def test_wholebody_to_coco18() -> None:
    wb = np.zeros((133, 3), dtype=np.float32)
    wb[0] = [50, 20, 0.9]  # nose
    wb[5] = [70, 40, 0.8]  # left shoulder
    wb[6] = [30, 40, 0.6]  # right shoulder
    wb[10] = [20, 90, 0.1]  # right wrist, too uncertain
    points = dwpose.to_coco18(wb, width=100, height=200)
    assert len(points) == len(KEYPOINTS)
    named = dict(zip(KEYPOINTS, points, strict=True))
    assert named["nose"] == (0.5, 0.1, 0.9)
    assert named["neck"] == (0.5, 0.2, pytest.approx(0.7))  # mid-shoulder
    assert named["right_shoulder"] == (0.3, 0.2, 0.6)
    assert named["left_shoulder"] == (0.7, 0.2, 0.8)
    assert named["right_wrist"] is None


def _fake_models(folder: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    data = {name: f"model {name}".encode() for name in dwpose.MODELS}
    folder.mkdir(parents=True, exist_ok=True)
    for name, body in data.items():
        (folder / name).write_bytes(body)
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in data.items()}
    monkeypatch.setattr(dwpose, "MODELS", hashes)
    monkeypatch.setattr(install, "MODELS", hashes)
    return data


def test_install_copies_and_verifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_models(tmp_path / "src", monkeypatch)
    target = tmp_path / "models"
    assert install.install(target, source_dir=tmp_path / "src", log=lambda _: None) == list(
        dwpose.MODELS
    )
    assert dwpose.DWPoseDetector.installed(target)
    # A second run keeps the verified files.
    assert install.install(target, source_dir=tmp_path / "src", log=lambda _: None) == []


def test_install_discards_a_corrupt_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_models(tmp_path / "unused", monkeypatch)
    urls: list[str] = []

    def serve(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, content=b"tampered")

    client = httpx.Client(transport=httpx.MockTransport(serve))
    with pytest.raises(install.InstallError, match="checksum mismatch"):
        install.install(tmp_path / "models", client=client, log=lambda _: None)
    assert urls == ["https://huggingface.co/yzd-v/DWPose/resolve/main/yolox_l.onnx"]
    assert list((tmp_path / "models").iterdir()) == []  # no .part file is left behind


def test_install_downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _fake_models(tmp_path / "unused", monkeypatch)
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=data[r.url.path.rsplit("/", 1)[-1]])
        )
    )
    install.install(tmp_path / "models", client=client, log=lambda _: None)
    assert sorted(p.name for p in (tmp_path / "models").iterdir()) == sorted(dwpose.MODELS)


def test_corrupt_model_is_not_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_models(tmp_path, monkeypatch)
    (tmp_path / dwpose.POSE_FILE).write_bytes(b"changed")
    with pytest.raises(Exception, match="checksum") as exc:
        dwpose.DWPoseDetector(tmp_path).detect(b"")
    assert getattr(exc.value, "code", None) == "POSE_MODEL_CORRUPT"


def test_default_detector_needs_both_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSET_STUDIO_POSE_MODELS_DIR", str(tmp_path))
    from asset_studio.config import get_settings

    get_settings.cache_clear()
    try:
        assert load_default_detector() is None
        _fake_models(tmp_path, monkeypatch)
        detector = load_default_detector()
        assert detector is not None and detector.name == "dwpose"
    finally:
        get_settings.cache_clear()


MODELS_DIR = os.environ.get("ASSET_STUDIO_TEST_POSE_MODELS", "")
IMAGE = os.environ.get("ASSET_STUDIO_TEST_POSE_IMAGE", "")


@pytest.mark.skipif(not (MODELS_DIR and IMAGE), reason="real DWPose models not provided")
def test_real_models_find_a_person() -> None:
    detector = dwpose.DWPoseDetector(MODELS_DIR)
    image = Path(IMAGE).read_bytes()
    found = detector.detect(image)
    assert found is not None, "no person found"
    visible = [p for p in found.keypoints if p is not None]
    assert len(visible) >= 8
    assert all(0 <= p[0] <= 1 and 0 <= p[1] <= 1 for p in visible)
    x0, y0, x1, y1 = found.box
    assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
    # With the box the user would draw, the result is the same person.
    boxed = detector.detect(image, found.box)
    assert boxed is not None and boxed.score == 1.0
