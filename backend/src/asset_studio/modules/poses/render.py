"""OpenPose skeleton image for the pose ControlNet (FR-033), as the WP-01 spike drew it.

The pose canvas (``aspect`` = width / height) is fitted into the target size and centred,
so a portrait pose stays a portrait figure on a square image.
"""

import io

from PIL import Image, ImageDraw

from asset_studio.modules.poses.skeleton import LIMBS, Point

COLOURS = (
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0),
    (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
    (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85),
)  # fmt: skip


def fit(aspect: float, width: int, height: int) -> tuple[float, float, float, float]:
    """Offset and size (x, y, w, h) of the pose canvas inside the target image."""
    if width / height > aspect:
        w, h = aspect * height, float(height)
    else:
        w, h = float(width), width / aspect
    return (width - w) / 2, (height - h) / 2, w, h


def openpose_png(keypoints: list[Point], aspect: float, width: int, height: int) -> bytes:
    ox, oy, w, h = fit(aspect, width, height)
    scale = min(width, height) / 1024
    limb, joint = max(2, round(8 * scale)), max(2, round(6 * scale))
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    def at(p: Point) -> tuple[float, float] | None:
        return None if p is None else (ox + p[0] * w, oy + p[1] * h)

    for i, (a, b) in enumerate(LIMBS):
        pa, pb = at(keypoints[a]), at(keypoints[b])
        if pa and pb:
            draw.line([pa, pb], fill=COLOURS[i], width=limb)
    for i, p in enumerate(keypoints):
        xy = at(p)
        if xy:
            x, y = xy
            draw.ellipse([x - joint, y - joint, x + joint, y + joint], fill=COLOURS[i])
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
