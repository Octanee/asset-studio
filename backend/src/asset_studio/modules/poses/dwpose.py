"""DWPose on the CPU with ONNX Runtime (ADR-009), ported from the WP-01 spike.

YOLOX-L finds the most confident person (unless the user drew a box), DW-LL estimates the
133 whole-body keypoints, and the body points are converted to COCO-18 (OpenPose order)
normalised to the image. The models load once, on first use, and stay loaded (the spike
measured 40-60 s to load and 2-5 s per image).
"""

import hashlib
import io
import threading
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from asset_studio.errors import DomainError
from asset_studio.modules.poses.detection import Box, Detection
from asset_studio.modules.poses.skeleton import KEYPOINTS, Point

DETECTOR_FILE = "yolox_l.onnx"
POSE_FILE = "dw-ll_ucoco_384.onnx"
# Upstream files of huggingface.co/yzd-v/DWPose (Apache-2.0), verified before loading.
MODELS = {
    DETECTOR_FILE: "7860ae79de6c89a3c1eb72ae9a2756c0ccfbe04b7791bb5880afabd97855a411",
    POSE_FILE: "724f4ff2439ed61afb86fb8a1951ec39c6220682803b4a8bd4f598cd913b1843",
}
DETECTOR_SIZE = 640
POSE_W, POSE_H = 288, 384
# The spike missed one standing figure at 0.3, so the person threshold is lower.
PERSON_THRESHOLD = 0.2
# Joints below this confidence are left out; the user adds them in the editor.
JOINT_THRESHOLD = 0.3

# COCO-WholeBody body index for each OpenPose COCO-18 joint; the neck is mid-shoulder.
_FROM_WHOLEBODY = (0, None, 6, 8, 10, 5, 7, 9, 12, 14, 16, 11, 13, 15, 2, 1, 4, 3)

Array = NDArray[np.float32]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def letterbox(rgb: NDArray[np.uint8], size: int = DETECTOR_SIZE) -> tuple[Array, float]:
    """Scale to fit a sizexsize square (top-left aligned, grey padding) as YOLOX expects."""
    h, w = rgb.shape[:2]
    r = min(size / h, size / w)
    resized = Image.fromarray(rgb).resize(
        (max(1, int(w * r)), max(1, int(h * r))), Image.Resampling.BILINEAR
    )
    pad = np.full((size, size, 3), 114, dtype=np.uint8)
    arr = np.asarray(resized)
    pad[: arr.shape[0], : arr.shape[1]] = arr
    return pad.astype(np.float32), r


def decode_yolox(out: Array, ratio: float, size: int = DETECTOR_SIZE) -> tuple[Array, Array]:
    """Raw YOLOX head output (N, 85) to person boxes (x0, y0, x1, y1) and scores."""
    grids, strides = [], []
    for s in (8, 16, 32):
        n = size // s
        yv, xv = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((n * n, 1), s))
    grid, stride = np.concatenate(grids), np.concatenate(strides)
    xy = (out[:, :2] + grid) * stride
    wh = np.exp(out[:, 2:4]) * stride
    scores = (out[:, 4] * out[:, 5]).astype(np.float32)  # objectness x person class
    boxes = np.concatenate([xy - wh / 2, xy + wh / 2], axis=1) / ratio
    return boxes.astype(np.float32), scores


def to_coco18(wholebody: Array, width: int, height: int) -> list[Point]:
    """133 whole-body keypoints in pixels (x, y, score) to normalised COCO-18."""
    points: list[Point] = []
    for index in _FROM_WHOLEBODY:
        kp = (wholebody[5] + wholebody[6]) / 2 if index is None else wholebody[index]
        x, y, conf = (float(v) for v in kp)
        if conf < JOINT_THRESHOLD or not (0 <= x <= width and 0 <= y <= height):
            points.append(None)
        else:
            points.append((round(x / width, 4), round(y / height, 4), round(min(conf, 1.0), 3)))
    if len(points) != len(KEYPOINTS):  # pragma: no cover - guards the mapping table
        raise ValueError("COCO-18 mapping is incomplete")
    return points


class DWPoseDetector:
    name = "dwpose"

    def __init__(self, models_dir: str | Path, *, verify: bool = True) -> None:
        self.models_dir = Path(models_dir)
        self.verify = verify
        self._lock = threading.Lock()
        self._sessions: tuple[Any, Any] | None = None

    @staticmethod
    def installed(models_dir: str | Path) -> bool:
        return all((Path(models_dir) / name).is_file() for name in MODELS)

    def _load(self) -> tuple[Any, Any]:
        with self._lock:
            if self._sessions is None:
                import onnxruntime as ort  # type: ignore[import-untyped]

                for name, expected in MODELS.items():
                    path = self.models_dir / name
                    if not path.is_file():
                        raise DomainError(
                            409, "POSE_DETECTOR_NOT_INSTALLED", f"Missing model file {name}."
                        )
                    if self.verify and sha256_of(path) != expected:
                        raise DomainError(
                            409, "POSE_MODEL_CORRUPT", f"{name} does not match its checksum."
                        )
                options = ort.SessionOptions()
                options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                cpu = ["CPUExecutionProvider"]
                self._sessions = (
                    ort.InferenceSession(
                        str(self.models_dir / DETECTOR_FILE), options, providers=cpu
                    ),
                    ort.InferenceSession(str(self.models_dir / POSE_FILE), options, providers=cpu),
                )
            return self._sessions

    def _person(self, session: Any, rgb: NDArray[np.uint8]) -> tuple[list[float], float] | None:
        pad, ratio = letterbox(rgb[:, :, ::-1].copy())  # YOLOX expects BGR, 0-255
        x = pad.transpose(2, 0, 1)[None]
        out = session.run(None, {session.get_inputs()[0].name: x})[0][0]
        boxes, scores = decode_yolox(out.astype(np.float32), ratio)
        best = int(np.argmax(scores))
        if scores[best] < PERSON_THRESHOLD:
            return None
        return [float(v) for v in boxes[best]], float(scores[best])

    @staticmethod
    def _pose(session: Any, rgb: NDArray[np.uint8], box: list[float]) -> Array:
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = (x1 - x0) * 1.25, (y1 - y0) * 1.25
        aspect = POSE_W / POSE_H
        w, h = (h * aspect, h) if w / h < aspect else (w, w / aspect)
        crop = Image.fromarray(rgb).crop(
            (int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2))
        )
        pixels = np.asarray(crop.resize((POSE_W, POSE_H), Image.Resampling.BILINEAR), np.float32)
        normed = (pixels - [123.675, 116.28, 103.53]) / [58.395, 57.12, 57.375]
        inp = normed.transpose(2, 0, 1)[None].astype(np.float32)
        simcc_x, simcc_y = session.run(None, {session.get_inputs()[0].name: inp})
        kx, ky = simcc_x[0].argmax(1) / 2.0, simcc_y[0].argmax(1) / 2.0  # split ratio 2
        conf = np.minimum(simcc_x[0].max(1), simcc_y[0].max(1))
        px = kx / POSE_W * w + (cx - w / 2)
        py = ky / POSE_H * h + (cy - h / 2)
        return np.stack([px, py, conf], 1).astype(np.float32)

    def detect(self, image: bytes, box: Box | None = None) -> Detection | None:
        detector, pose = self._load()
        with Image.open(io.BytesIO(image)) as img:
            rgb = np.asarray(img.convert("RGB"))
        height, width = rgb.shape[:2]
        if box is not None:
            pixels = [box[0] * width, box[1] * height, box[2] * width, box[3] * height]
            score = 1.0
        else:
            found = self._person(detector, rgb)
            if found is None:
                return None
            pixels, score = found
        keypoints = to_coco18(self._pose(pose, rgb, pixels), width, height)
        norm = (
            max(0.0, pixels[0] / width),
            max(0.0, pixels[1] / height),
            min(1.0, pixels[2] / width),
            min(1.0, pixels[3] / height),
        )
        return Detection(
            keypoints=keypoints,
            score=score,
            box=(round(norm[0], 4), round(norm[1], 4), round(norm[2], 4), round(norm[3], 4)),
        )
