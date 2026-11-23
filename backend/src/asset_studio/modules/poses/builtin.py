"""Built-in poses (FR-020): rows with ``project_id`` null, seeded by migration 0004.

Ids are fixed (uuid5 of the slug), so a generation that used a built-in pose can always be
traced back to it. Coordinates are for a 3:4 portrait canvas.
"""

import uuid
from dataclasses import dataclass

from asset_studio.modules.poses.skeleton import KEYPOINTS, Point

NAMESPACE = uuid.UUID("7b0e4f1c-3f1e-4c55-9a43-5d0b8f2a6e10")
ASPECT = 0.75


@dataclass(frozen=True)
class BuiltinPose:
    slug: str
    name: str
    view: str
    keypoints: list[Point]

    @property
    def id(self) -> uuid.UUID:
        return uuid.uuid5(NAMESPACE, self.slug)


def _points(**joints: tuple[float, float]) -> list[Point]:
    unknown = set(joints) - set(KEYPOINTS)
    if unknown:
        raise ValueError(f"unknown joints: {sorted(unknown)}")
    return [(*joints[k], 1.0) if k in joints else None for k in KEYPOINTS]


_HEAD = {
    "nose": (0.50, 0.14),
    "neck": (0.50, 0.22),
    "right_eye": (0.48, 0.125),
    "left_eye": (0.52, 0.125),
    "right_ear": (0.46, 0.135),
    "left_ear": (0.54, 0.135),
}
_SHOULDERS = {"right_shoulder": (0.40, 0.23), "left_shoulder": (0.60, 0.23)}
_LEGS = {
    "right_hip": (0.44, 0.50),
    "right_knee": (0.44, 0.68),
    "right_ankle": (0.44, 0.86),
    "left_hip": (0.56, 0.50),
    "left_knee": (0.56, 0.68),
    "left_ankle": (0.56, 0.86),
}


def _shift(joints: dict[str, tuple[float, float]], dy: float) -> dict[str, tuple[float, float]]:
    return {k: (x, round(y + dy, 4)) for k, (x, y) in joints.items()}


BUILTIN_POSES = (
    BuiltinPose(
        "standing",
        "Standing",
        "front",
        _points(
            **_HEAD,
            **_SHOULDERS,
            right_elbow=(0.37, 0.36),
            right_wrist=(0.36, 0.48),
            left_elbow=(0.63, 0.36),
            left_wrist=(0.64, 0.48),
            **_LEGS,
        ),
    ),
    BuiltinPose(
        "t-pose",
        "T-pose",
        "front",
        _points(
            **_HEAD,
            **_SHOULDERS,
            right_elbow=(0.28, 0.23),
            right_wrist=(0.16, 0.23),
            left_elbow=(0.72, 0.23),
            left_wrist=(0.84, 0.23),
            **_LEGS,
        ),
    ),
    BuiltinPose(
        "arms-up",
        "Arms up",
        "front",
        _points(
            **_HEAD,
            **_SHOULDERS,
            right_elbow=(0.37, 0.12),
            right_wrist=(0.38, 0.03),
            left_elbow=(0.63, 0.12),
            left_wrist=(0.62, 0.03),
            **_LEGS,
        ),
    ),
    BuiltinPose(
        "squat",
        "Squat",
        "front",
        _points(
            **_shift({**_HEAD, **_SHOULDERS}, 0.18),
            right_elbow=(0.40, 0.52),
            right_wrist=(0.45, 0.56),
            left_elbow=(0.60, 0.52),
            left_wrist=(0.55, 0.56),
            right_hip=(0.43, 0.66),
            right_knee=(0.33, 0.70),
            right_ankle=(0.40, 0.86),
            left_hip=(0.57, 0.66),
            left_knee=(0.67, 0.70),
            left_ankle=(0.60, 0.86),
        ),
    ),
    BuiltinPose(
        "standing-side",
        "Standing, side",
        "right",
        _points(
            nose=(0.56, 0.14),
            neck=(0.50, 0.22),
            right_eye=(0.54, 0.125),
            right_ear=(0.49, 0.13),
            right_shoulder=(0.50, 0.23),
            right_elbow=(0.50, 0.36),
            right_wrist=(0.52, 0.48),
            left_shoulder=(0.50, 0.23),
            left_elbow=(0.49, 0.36),
            left_wrist=(0.50, 0.48),
            right_hip=(0.50, 0.50),
            right_knee=(0.51, 0.68),
            right_ankle=(0.50, 0.86),
            left_hip=(0.50, 0.50),
            left_knee=(0.50, 0.68),
            left_ankle=(0.49, 0.86),
        ),
    ),
)
