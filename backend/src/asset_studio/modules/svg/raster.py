"""Rasterising SVG with resvg (FR-047, ADR-006): thumbnails, validation and export.

Only cleaned SVG is rendered (``sanitize.clean`` runs again here), with system fonts
skipped and no resource folder, so a render never reads a file or the network.
"""

import resvg_py

from asset_studio.modules.svg.sanitize import SvgError, clean

MAX_SIDE = 4096
SVG_MIME = "image/svg+xml"


def is_svg(mime: str | None) -> bool:
    return mime == SVG_MIME


def render(data: bytes | str, width: int, height: int) -> bytes:
    """A PNG that fits in ``width`` x ``height``, keeping the viewBox's aspect ratio."""
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
        raise SvgError("SVG_SIZE", f"Render sizes are 1 to {MAX_SIDE} pixels.")
    svg = clean(data).svg
    try:
        return bytes(
            resvg_py.svg_to_bytes(
                svg_string=svg, width=width, height=height, skip_system_fonts=True
            )
        )
    except ValueError as exc:
        raise SvgError("SVG_RENDER_FAILED", "The SVG could not be rendered.") from exc
