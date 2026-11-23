"""Image post-processing with Pillow (FR-065): cut-out, background, resize, convert, optimise,
and the derived thumbnail and preview. Pure functions over bytes, so they are easy to test.
"""

import io
from dataclasses import dataclass, field
from typing import Any, Literal

from PIL import Image, ImageOps

Background = Literal["any", "white", "transparent"]
Resize = Literal["contain", "cover", "none"]
Format = Literal["png", "webp", "jpeg"]

MIME = {"png": "image/png", "webp": "image/webp", "jpeg": "image/jpeg"}
EXT = {"png": "png", "webp": "webp", "jpeg": "jpg"}
WHITE = (255, 255, 255)
# Decompression bombs: outputs are at most 4096² (OutputDefaults).
MAX_PIXELS = 4096 * 4096 * 2


class ProcessingError(ValueError):
    """The input cannot be processed; ``code`` is stable and safe to show."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class Target:
    width: int
    height: int
    format: Format
    background: Background
    resize: Resize = "contain"
    optimize: bool = True
    quality: int = 90


@dataclass
class Result:
    data: bytes
    mime: str
    ext: str
    width: int
    height: int
    steps: list[dict[str, Any]] = field(default_factory=list)


def open_image(data: bytes) -> Image.Image:
    """Decode fully (integrity); raise ProcessingError for broken or huge files."""
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_PIXELS:
            raise ProcessingError("IMAGE_TOO_LARGE", "The image has too many pixels.")
        image.load()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        if isinstance(exc, ProcessingError):
            raise
        raise ProcessingError("IMAGE_UNREADABLE", "The image cannot be decoded.") from exc
    return image


def has_alpha(image: Image.Image) -> bool:
    return image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)


def cutout(original: bytes, mask: bytes) -> bytes:
    """The original with the mask as its alpha channel (white = keep), as PNG."""
    image = ImageOps.exif_transpose(open_image(original)).convert("RGB")
    alpha = open_image(mask).convert("L")
    if alpha.size != image.size:
        alpha = alpha.resize(image.size, Image.Resampling.BICUBIC)
    image.putalpha(alpha)
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def _flatten(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    base = Image.new("RGBA", rgba.size, (*WHITE, 255))
    base.alpha_composite(rgba)
    return base.convert("RGB")


def _resize(image: Image.Image, t: Target, steps: list[dict[str, Any]]) -> Image.Image:
    size = (t.width, t.height)
    if t.resize == "none" or image.size == size:
        return image
    before = list(image.size)
    if t.resize == "cover":
        image = ImageOps.fit(image, size, Image.Resampling.LANCZOS)
    else:
        fitted = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
        fill: tuple[int, ...] = (0, 0, 0, 0) if image.mode == "RGBA" else WHITE
        canvas = Image.new(image.mode, size, fill)
        canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
        image = canvas
    steps.append({"step": "resize", "mode": t.resize, "from": before, "to": list(size)})
    return image


def process(data: bytes, t: Target, *, source_format: str | None = None) -> Result:
    """Apply the project's processing to one image (the original, or its cut-out after
    background removal; ``source_format`` is then the original's format)."""
    steps: list[dict[str, Any]] = []
    source = open_image(data)
    source_format = source_format or (source.format or "").lower()
    image = ImageOps.exif_transpose(source)
    # Work in RGB or RGBA only.
    image = image.convert("RGBA") if has_alpha(image) else image.convert("RGB")
    if t.background == "white" and image.mode == "RGBA":
        image = _flatten(image)
        steps.append({"step": "background", "fill": "white"})
    image = _resize(image, t, steps)
    if t.format == "jpeg" and image.mode == "RGBA":  # JPEG has no alpha channel
        image = _flatten(image)
        steps.append({"step": "background", "fill": "white", "reason": "jpeg"})

    out = io.BytesIO()
    if t.format == "png":
        image.save(out, "PNG", optimize=t.optimize)
    elif t.format == "webp":
        image.save(out, "WEBP", quality=t.quality, method=6 if t.optimize else 4)
    else:
        image.save(out, "JPEG", quality=t.quality, optimize=t.optimize, progressive=t.optimize)
    if source_format != t.format:
        steps.append({"step": "convert", "from": source_format or None, "to": t.format})
    if t.optimize:
        steps.append({"step": "optimize", "quality": None if t.format == "png" else t.quality})
    return Result(
        data=out.getvalue(),
        mime=MIME[t.format],
        ext=EXT[t.format],
        width=image.width,
        height=image.height,
        steps=steps,
    )


def derived(data: bytes, side: int) -> bytes:
    """A WebP that fits in ``side``² for the library grid (thumb 256) and review (1024)."""
    image = open_image(data)
    image = image.convert("RGBA") if has_alpha(image) else image.convert("RGB")
    image.thumbnail((side, side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "WEBP", quality=82, method=4)
    return out.getvalue()
