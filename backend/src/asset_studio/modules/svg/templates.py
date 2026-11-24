"""Built-in SVG templates (FR-045): versioned code, deterministic output.

A template is a function of its parameters only: the same template version and the same
parameters always give the same file. Changing what a template draws means a new version,
so a stored version can always say exactly what made it (RULE-011).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from asset_studio.errors import DomainError

ParamKind = Literal["glyph", "color", "number"]
HEX = re.compile(r"#[0-9a-fA-F]{6}")
NS = 'xmlns="http://www.w3.org/2000/svg"'

# Line glyphs on a 24-unit grid.
GLYPHS: dict[str, str] = {
    "dumbbell": "M6 7v10M18 7v10M3 10v4M21 10v4M6 12h12",
    "heart": "M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z",
    "timer": "M12 9v4l3 2M9 2h6M12 22a8 8 0 1 0 0-16 8 8 0 0 0 0 16z",
    "play": "M8 5l11 7-11 7z",
    "check": "M5 12.5l4.5 4.5L19 7",
    "plus": "M12 5v14M5 12h14",
    "star": "M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9z",
    "flame": "M12 21a6 6 0 0 0 6-6c0-4-3-6-4-10-2 2-3 4-3 6-1-1-2-2-2-4-2 2-3 4.5-3 8a6 6 0 0 0 6 "
    "6z",
}


@dataclass(frozen=True)
class Param:
    name: str
    kind: ParamKind
    default: str | float
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Template:
    id: str
    version: int
    name: str
    description: str
    params: tuple[Param, ...]
    draw: Callable[[dict[str, Any]], str] = field(repr=False)

    def defaults(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.params}


def _n(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _icon(p: dict[str, Any]) -> str:
    return (
        f'<svg {NS} viewBox="0 0 24 24"><path d="{GLYPHS[p["glyph"]]}" fill="none" '
        f'stroke="{p["color"]}" stroke-width="{_n(p["stroke_width"])}" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def _badge(p: dict[str, Any]) -> str:
    scale = 0.55
    return (
        f'<svg {NS} viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="{p["color"]}"/>'
        f'<path d="{GLYPHS[p["glyph"]]}" fill="none" stroke="{p["glyph_color"]}" '
        f'stroke-width="{_n(p["stroke_width"] / scale)}" stroke-linecap="round" '
        f'stroke-linejoin="round" transform="translate(5.4 5.4) scale({scale})"/></svg>'
    )


def _dots(p: dict[str, Any]) -> str:
    gap = p["spacing"]
    count = max(1, round(24 / gap))
    side = gap * count  # a whole number of cells, so the tile repeats without a seam
    dots = "".join(
        f'<circle cx="{_n(gap * (i + 0.5))}" cy="{_n(gap * (j + 0.5))}" r="{_n(p["dot"])}"/>'
        for j in range(count)
        for i in range(count)
    )
    return f'<svg {NS} viewBox="0 0 {_n(side)} {_n(side)}"><g fill="{p["color"]}">{dots}</g></svg>'


GLYPH = Param("glyph", "glyph", "dumbbell", options=tuple(GLYPHS))
STROKE = Param("stroke_width", "number", 2.0, min=1, max=3, step=0.25)
TEMPLATES: dict[str, Template] = {
    t.id: t
    for t in (
        Template(
            "icon-line",
            1,
            "Icon — rounded line",
            "One glyph in a rounded line style.",
            (GLYPH, Param("color", "color", "#1f2a44"), STROKE),
            _icon,
        ),
        Template(
            "badge-circle",
            1,
            "Badge — circle",
            "A glyph on a filled circle.",
            (
                GLYPH,
                Param("color", "color", "#2bb3a3"),
                Param("glyph_color", "color", "#ffffff"),
                STROKE,
            ),
            _badge,
        ),
        Template(
            "pattern-dots",
            1,
            "Pattern — dot grid",
            "A tileable background of dots.",
            (
                Param("color", "color", "#1f2a44"),
                Param("spacing", "number", 5, min=3, max=8, step=1),
                Param("dot", "number", 0.8, min=0.3, max=1.6, step=0.1),
            ),
            _dots,
        ),
    )
}


def get_template(template_id: str) -> Template:
    template = TEMPLATES.get(template_id)
    if template is None:
        raise DomainError(
            404, "SVG_TEMPLATE_NOT_FOUND", "SVG template not found.", {"template_id": template_id}
        )
    return template


def _invalid(name: str, detail: str) -> DomainError:
    return DomainError(422, "SVG_PARAM_INVALID", f"{name}: {detail}", {"param": name})


def normalise(template: Template, raw: dict[str, Any]) -> dict[str, Any]:
    """The template's parameters with defaults filled in, checked and in one canonical form."""
    known = {p.name for p in template.params}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise DomainError(
            422, "SVG_PARAM_UNKNOWN", "Unknown template parameters.", {"params": unknown}
        )
    out: dict[str, Any] = {}
    for p in template.params:
        value = raw.get(p.name, p.default)
        if p.kind == "glyph":
            if value not in p.options:
                raise _invalid(p.name, "unknown glyph")
        elif p.kind == "color":
            if not isinstance(value, str) or not HEX.fullmatch(value):
                raise _invalid(p.name, "a colour is #rrggbb")
            value = value.lower()
        else:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise _invalid(p.name, "a number is expected")
            if p.min is not None and p.max is not None and not p.min <= value <= p.max:
                raise _invalid(p.name, f"between {p.min:g} and {p.max:g}")
            value = round(float(value), 3)
        out[p.name] = value
    return out
