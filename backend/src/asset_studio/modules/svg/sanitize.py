"""SVG sanitising and optimising (FR-046, NFR-011, Security-Architecture).

Every SVG the studio stores passes through ``clean``: an allow-list of shape elements and
presentation attributes. Anything else is dropped and counted: scripts, ``style``, event
handlers, foreign namespaces, links (``href``), images, text and external ``url()``
references. A DOCTYPE or entity declaration is refused outright, so the XML parser never
expands entities. The result is written out again in one compact, deterministic form
(numbers rounded to three decimals, no comments or whitespace), which is the optimisation.
"""

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

SVG_NS = "http://www.w3.org/2000/svg"
MAX_BYTES = 512 * 1024
MAX_ELEMENTS = 5000
MAX_DEPTH = 32
MAX_VALUE = 20_000

PAINT = {"fill", "stroke", "stop-color"}
PRESENTATION = PAINT | {
    "fill-opacity",
    "fill-rule",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-opacity",
    "stroke-miterlimit",
    "stroke-dasharray",
    "stroke-dashoffset",
    "stop-opacity",
    "opacity",
    "transform",
    "clip-rule",
}
ELEMENTS: dict[str, set[str]] = {
    "svg": {"viewBox", "width", "height", "preserveAspectRatio"},
    "g": set(),
    "defs": set(),
    "path": {"d"},
    "circle": {"cx", "cy", "r"},
    "ellipse": {"cx", "cy", "rx", "ry"},
    "rect": {"x", "y", "width", "height", "rx", "ry"},
    "line": {"x1", "y1", "x2", "y2"},
    "polyline": {"points"},
    "polygon": {"points"},
    "linearGradient": {"x1", "y1", "x2", "y2", "gradientUnits", "gradientTransform"},
    "radialGradient": {"cx", "cy", "r", "fx", "fy", "gradientUnits", "gradientTransform"},
    "stop": {"offset"},
    "title": set(),
    "desc": set(),
}
TEXT_ELEMENTS = {"title", "desc"}
CONTAINERS = {"g", "defs"}
# Attributes whose numbers are rounded; the rest keep their value as written.
GEOMETRY = {
    "d", "points", "transform", "gradientTransform", "viewBox", "width", "height", "x", "y",
    "cx", "cy", "r", "rx", "ry", "fx", "fy", "x1", "y1", "x2", "y2", "stroke-width",
    "stroke-dasharray", "stroke-dashoffset", "offset",
}  # fmt: skip
ID = re.compile(r"[A-Za-z_][\w.-]{0,63}")
PAINT_VALUE = re.compile(
    r"none|currentColor|#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,24}|url\(#[A-Za-z_][\w.-]{0,63}\)"
)
# Plain values: numbers, units, keywords, lists and transform functions; no url(), quotes,
# colons or angle brackets.
PLAIN_VALUE = re.compile(r"[0-9A-Za-z.,+\-\s()%]*")
NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
DECLARATION = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)", re.IGNORECASE)


class SvgError(ValueError):
    """The SVG cannot be used; ``code`` is stable and safe to show."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class Clean:
    svg: str
    width: float  # the viewBox size
    height: float
    removed_elements: int
    removed_attributes: int
    bytes_in: int
    bytes_out: int

    @property
    def report(self) -> dict[str, int]:
        return {
            "removed_elements": self.removed_elements,
            "removed_attributes": self.removed_attributes,
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
        }


def _number(match: re.Match[str]) -> str:
    text = f"{float(match.group(0)):.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _value(name: str, raw: str) -> str | None:
    """The cleaned value, or None when the attribute must go."""
    value = " ".join(raw.split())
    if len(value) > MAX_VALUE:
        return None
    if name == "id":
        return value if ID.fullmatch(value) else None
    if name in PAINT:
        return value if PAINT_VALUE.fullmatch(value) else None
    if not PLAIN_VALUE.fullmatch(value):
        return None
    if name in GEOMETRY:
        value = NUMBER.sub(_number, value)
    return value


def _view_box(value: str | None) -> tuple[float, float]:
    parts = (value or "").replace(",", " ").split()
    try:
        numbers = [float(p) for p in parts]
    except ValueError:
        numbers = []
    if len(numbers) != 4 or numbers[2] <= 0 or numbers[3] <= 0:
        raise SvgError("SVG_VIEWBOX", "The SVG needs a viewBox with a positive width and height.")
    return numbers[2], numbers[3]


class _Writer:
    def __init__(self) -> None:
        self.removed_elements = 0
        self.removed_attributes = 0
        self.count = 0

    def attributes(self, element: ET.Element, local: str) -> list[tuple[str, str]]:
        allowed = ELEMENTS[local] | PRESENTATION | {"id"}
        out = []
        for key, raw in element.attrib.items():
            value = _value(key, raw) if key in allowed else None
            if value is None:
                self.removed_attributes += 1
            else:
                out.append((key, value))
        return out

    def element(self, element: ET.Element, depth: int) -> str:
        """The element written out, or "" when it is dropped."""
        tag = element.tag if isinstance(element.tag, str) else ""
        local = tag[len(SVG_NS) + 2 :] if tag.startswith(f"{{{SVG_NS}}}") else ""
        if local not in ELEMENTS or local == "svg":
            self.removed_elements += sum(1 for _ in element.iter())
            return ""
        self.count += 1
        if self.count > MAX_ELEMENTS or depth > MAX_DEPTH:
            raise SvgError("SVG_TOO_COMPLEX", "The SVG has too many or too deeply nested elements.")
        attrs = self.attributes(element, local)
        if local in TEXT_ELEMENTS:
            self.removed_elements += sum(1 for _ in element.iter()) - 1
            text = " ".join((element.text or "").split())[:500]
            return f"<{local}>{escape(text)}</{local}>" if text else ""
        inner = "".join(self.element(child, depth + 1) for child in element)
        if local in CONTAINERS and not inner:
            return ""  # an empty group or defs draws nothing
        head = local + "".join(f" {k}={quoteattr(v)}" for k, v in attrs)
        return f"<{head}>{inner}</{local}>" if inner else f"<{head}/>"


def clean(data: bytes | str) -> Clean:
    raw = data.encode() if isinstance(data, str) else data
    if len(raw) > MAX_BYTES:
        raise SvgError("SVG_TOO_LARGE", f"The SVG is larger than {MAX_BYTES // 1024} kB.")
    if DECLARATION.search(raw):
        raise SvgError("SVG_DOCTYPE", "SVG files with a DOCTYPE or entities are not accepted.")
    try:
        root = ET.fromstring(raw.decode("utf-8"))  # noqa: S314 - DTDs refused above
    except (UnicodeDecodeError, ET.ParseError) as exc:
        raise SvgError("SVG_INVALID", "The file is not well-formed SVG.") from exc
    if root.tag != f"{{{SVG_NS}}}svg":
        raise SvgError("SVG_INVALID", "The root element is not an SVG element.")
    width, height = _view_box(root.attrib.get("viewBox"))
    writer = _Writer()
    attrs = writer.attributes(root, "svg")
    inner = "".join(writer.element(child, 1) for child in root)
    head = f"svg xmlns={quoteattr(SVG_NS)}" + "".join(f" {k}={quoteattr(v)}" for k, v in attrs)
    svg = f"<{head}>{inner}</svg>"
    return Clean(
        svg=svg,
        width=width,
        height=height,
        removed_elements=writer.removed_elements,
        removed_attributes=writer.removed_attributes,
        bytes_in=len(raw),
        bytes_out=len(svg.encode()),
    )
