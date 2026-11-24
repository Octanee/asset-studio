"""Technical validation rules (FR-060): pure checks over the processed file.

Results are informative: they never claim domain correctness and never replace visual review
(RULE-009). Each rule is ``passed``, ``failed`` or ``skipped`` (not configured / not
applicable), with details a person can read.
"""

import hashlib
import io
import re
from dataclasses import dataclass
from typing import Any

from PIL import Image

RULES = (
    "integrity",
    "format",
    "dimensions",
    "aspect_ratio",
    "file_size",
    "transparency",
    "naming",
)
FORMATS = {"PNG": "png", "WEBP": "webp", "JPEG": "jpeg"}
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MAX_NAME = 120
# Background checks look at a ring around the edge: the subject is usually in the middle.
RING = 0.04
TRANSPARENT_ALPHA = 16
WHITE_MIN = 240
EDGE_SHARE = 0.9


@dataclass(frozen=True)
class Expectations:
    width: int
    height: int
    format: str
    background: str  # any / white / transparent
    max_file_kb: int | None
    aspect_tolerance: float
    sha256: str
    file_name: str
    collisions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleResult:
    rule: str
    status: str
    details: dict[str, Any]


def render_name(pattern: str, values: dict[str, str]) -> str:
    """The project's naming pattern (``{asset}-{view}``) with values written in."""
    return re.sub(r"\{([a-z_]+)\}", lambda m: values.get(m.group(1), m.group(0)), pattern)


def _edge(image: Image.Image) -> list[tuple[int, int, int, int]]:
    rgba = image.convert("RGBA")
    w, h = rgba.size
    band = max(1, round(min(w, h) * RING))
    step = max(1, min(w, h) // 256)  # sample, so 4096² stays fast
    out: list[tuple[int, int, int, int]] = []
    for y in range(0, h, step):
        for x in range(0, w, step):
            if x < band or y < band or x >= w - band or y >= h - band:
                r, g, b, a = rgba.getpixel((x, y))  # type: ignore[misc]
                out.append((r, g, b, a))
    return out


def _transparency(image: Image.Image, background: str) -> RuleResult:
    if background == "any":
        return RuleResult("transparency", "skipped", {"background": "any"})
    alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
    edge = _edge(image)
    n = max(len(edge), 1)
    if background == "transparent":
        share = sum(1 for p in edge if p[3] < TRANSPARENT_ALPHA) / n
        return RuleResult(
            "transparency",
            "passed" if alpha and share >= EDGE_SHARE else "failed",
            {
                "background": "transparent",
                "alpha_channel": alpha,
                "transparent_edge": round(share, 3),
            },
        )
    white = sum(1 for p in edge if p[3] >= 255 - TRANSPARENT_ALPHA and min(p[:3]) >= WHITE_MIN)
    opaque = all(p[3] >= 255 - TRANSPARENT_ALPHA for p in edge)
    share = white / n
    return RuleResult(
        "transparency",
        "passed" if opaque and share >= EDGE_SHARE else "failed",
        {"background": "white", "white_edge": round(share, 3), "opaque_edge": opaque},
    )


def validate(data: bytes, e: Expectations, *, picture: bytes | None = None) -> list[RuleResult]:
    """Check ``data``. For a vector, ``picture`` is its render at the output size: the
    pixel rules look at the render, integrity and file size at the SVG itself."""
    digest = hashlib.sha256(data).hexdigest()
    try:
        image = Image.open(io.BytesIO(picture if picture is not None else data))
        image.load()
    except (OSError, ValueError, Image.DecompressionBombError):
        return [RuleResult("integrity", "failed", {"decoded": False})] + [
            RuleResult(rule, "skipped", {"reason": "unreadable"}) for rule in RULES[1:]
        ]
    results = [
        RuleResult(
            "integrity",
            "passed" if digest == e.sha256 else "failed",
            {"decoded": True, "sha256_matches": digest == e.sha256},
        )
    ]
    if picture is not None:
        # A vector is rasterised to the preset's format on export (FR-047).
        results.append(
            RuleResult(
                "format", "skipped", {"expected": e.format, "actual": "svg", "reason": "vector"}
            )
        )
    else:
        actual = FORMATS.get(image.format or "", (image.format or "").lower())
        results.append(
            RuleResult(
                "format",
                "passed" if actual == e.format else "failed",
                {"expected": e.format, "actual": actual},
            )
        )
    size = [image.width, image.height]
    results.append(
        RuleResult(
            "dimensions",
            "passed" if size == [e.width, e.height] else "failed",
            {"expected": [e.width, e.height], "actual": size},
        )
    )
    want, got = e.width / e.height, image.width / image.height
    results.append(
        RuleResult(
            "aspect_ratio",
            "passed" if abs(got - want) / want <= e.aspect_tolerance else "failed",
            {"expected": round(want, 4), "actual": round(got, 4), "tolerance": e.aspect_tolerance},
        )
    )
    if e.max_file_kb is None:
        results.append(RuleResult("file_size", "skipped", {"bytes": len(data)}))
    else:
        ok = len(data) <= e.max_file_kb * 1024
        results.append(
            RuleResult(
                "file_size",
                "passed" if ok else "failed",
                {"bytes": len(data), "max_kb": e.max_file_kb},
            )
        )
    results.append(_transparency(image, e.background))
    problems = []
    if not SAFE_NAME.fullmatch(e.file_name):
        problems.append("characters")
    if len(e.file_name) > MAX_NAME:
        problems.append("length")
    if e.collisions:
        problems.append("collision")
    results.append(
        RuleResult(
            "naming",
            "failed" if problems else "passed",
            {"name": e.file_name, "problems": problems, "same_as": list(e.collisions)[:10]},
        )
    )
    return results
