"""Pose detection from an image (FR-022, ADR-009).

The worker runs a ``PoseDetector`` in a ``detect_pose`` job on the CPU lane: DWPose (ONNX
Runtime on CPU, ``dwpose.py``) once its model files are installed (``python -m
asset_studio.modules.poses.install``). Without them ``get_detector`` returns None, the job
fails with ``POSE_DETECTOR_NOT_INSTALLED`` and the pose is set by hand in the editor.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from asset_studio.config import get_settings
from asset_studio.modules.poses.skeleton import Point

Box = tuple[float, float, float, float]  # x0, y0, x1, y1, normalised


@dataclass(frozen=True)
class Detection:
    keypoints: list[Point]
    score: float  # person detector confidence; 1.0 when the user drew the box
    box: Box


class PoseDetector(Protocol):
    name: str

    def detect(self, image: bytes, box: Box | None = None) -> Detection | None:
        """Return the most confident person, or None if nobody was found.

        ``box`` skips the person detector: the user drew it because detection missed.
        """
        ...


_detector: PoseDetector | None = None


def get_detector() -> PoseDetector | None:
    return _detector


def models_dir() -> Path:
    settings = get_settings()
    return Path(settings.pose_models_dir or Path(settings.data_dir) / "models" / "pose")


def load_default_detector() -> PoseDetector | None:
    """DWPose when its model files are installed, else None (the editor is the fallback)."""
    from asset_studio.modules.poses.dwpose import DWPoseDetector

    path = models_dir()
    return DWPoseDetector(path) if DWPoseDetector.installed(path) else None


def set_detector(detector: PoseDetector | None) -> None:
    """Install the detector the worker uses (tests and the DWPose integration)."""
    global _detector
    _detector = detector
