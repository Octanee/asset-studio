"""Pose detection from an image (FR-022, ADR-009).

The worker runs a ``PoseDetector`` in a ``detect_pose`` job on the CPU lane. DWPose (ONNX
Runtime on CPU) is the planned implementation; it needs extra packages and model files that
are installed only after the user approves them. Until then ``get_detector`` returns None
and the job fails with ``POSE_DETECTOR_NOT_INSTALLED``, and the pose is set by hand in the
editor (the manual fallback from the WP-01 spike).
"""

from dataclasses import dataclass
from typing import Protocol

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


def set_detector(detector: PoseDetector | None) -> None:
    """Install the detector the worker uses (tests and the DWPose integration)."""
    global _detector
    _detector = detector
