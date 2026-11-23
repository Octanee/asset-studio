"""COCO-18 skeleton in OpenPose body order (ADR-009), shared by the editor and ControlNet.

A pose is 18 keypoints, each ``[x, y, confidence]`` with x and y normalised to 0..1 of the
canvas (``aspect`` = width / height), or ``None`` when the joint is not visible.
"""

from typing import Annotated

from pydantic import Field

KEYPOINTS = (
    "nose",
    "neck",
    "right_shoulder",
    "right_elbow",
    "right_wrist",
    "left_shoulder",
    "left_elbow",
    "left_wrist",
    "right_hip",
    "right_knee",
    "right_ankle",
    "left_hip",
    "left_knee",
    "left_ankle",
    "right_eye",
    "left_eye",
    "right_ear",
    "left_ear",
)
LIMBS = (
    (1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10),
    (1, 11), (11, 12), (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17),
)  # fmt: skip
# Index of the same joint on the other side, for mirroring.
MIRROR = (0, 1, 5, 6, 7, 2, 3, 4, 11, 12, 13, 8, 9, 10, 15, 14, 17, 16)
VIEWS = ("front", "back", "left", "right", "three_quarter", "other")

Unit = Annotated[float, Field(ge=0, le=1)]
Point = tuple[Unit, Unit, Unit] | None
Keypoints = Annotated[list[Point], Field(min_length=18, max_length=18)]


def mirror(points: list[Point]) -> list[Point]:
    """Flip horizontally and swap left and right joints."""
    out: list[Point] = [None] * len(KEYPOINTS)
    for i, p in enumerate(points):
        out[MIRROR[i]] = None if p is None else (round(1 - p[0], 4), p[1], p[2])
    return out


def visible(points: list[Point], threshold: float = 0.0) -> int:
    return sum(1 for p in points if p is not None and p[2] > threshold)
