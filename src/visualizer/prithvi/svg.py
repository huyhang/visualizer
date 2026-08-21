"""Turning an uploaded SVG into one Prithvi is willing to store and serve back.

An uploaded map is hostile input that will later be handed to a browser, so this
module answers one question: what is the smallest subset of SVG that still draws
a map? Everything outside that subset is removed and *reported*, because the
brief was to strip unsafe content rather than reject the file -- and a writer who
exported from Inkscape deserves to be told what went missing rather than left to
notice a blank patch later.

Three decisions worth knowing about:

**Elements are allowed by list, not refused by list.** A refusal list is only as
good as its author's memory of the SVG specification, and the specification keeps
growing. Anything not named in ``_ALLOWED_ELEMENTS`` goes, which means a new
scripting vector added to SVG next year is already excluded here.

**Filter primitives stay.** They are the one exotic corner that earns its place:
hill shading a map is done by blurring an alpha channel and lighting the result,
so ``feGaussianBlur``/``feDiffuseLighting``/``feDistantLight`` are load-bearing
for the drawings this service exists to hold. ``feImage`` is the exception, since
it can pull in a document.

**Inline ``style`` survives, filtered.** Every real export leans on it, and
dropping the attribute wholesale turns a finished map into grey outlines. So the
value is inspected instead: scripting URLs, ``expression()``, ``@import`` and any
``url()`` that is not a same-document fragment take the attribute with them. This
is the one rule here enforced by inspecting a value rather than by structure,
which is why served SVG also carries a sandboxed, default-deny content security
policy -- if a value ever slips past this, it still cannot fetch or execute.

Parsing uses the standard library. ``xml.etree`` is not hardened against entity
expansion, so documents declaring a DTD or an entity are refused outright before
a parser ever sees them, and nesting is capped.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .errors import InvalidSvg, SvgTooLarge
from .models import ViewBox

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"

MAX_DEPTH = 100

_STRUCTURE = {"svg", "g", "defs", "symbol", "use", "switch", "title", "desc", "a"}
_SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
_TEXT = {"text", "tspan", "textpath"}
_PAINT = {
    "lineargradient",
    "radialgradient",
    "stop",
    "pattern",
    "marker",
    "clippath",
    "mask",
}
# Every filter primitive except ``feImage``, which can reference a document.
_FILTERS = {
    "filter",
    "feblend",
    "fecolormatrix",
    "fecomponenttransfer",
    "fecomposite",
    "feconvolvematrix",
    "fediffuselighting",
    "fedisplacementmap",
    "fedistantlight",
    "fedropshadow",
    "feflood",
    "fefunca",
    "fefuncb",
    "fefuncg",
    "fefuncr",
    "fegaussianblur",
    "femerge",
    "femergenode",
    "femorphology",
    "feoffset",
    "fepointlight",
    "fespecularlighting",
    "fespotlight",
    "fetile",
    "feturbulence",
}
_ALLOWED_ELEMENTS = _STRUCTURE | _SHAPES | _TEXT | _PAINT | _FILTERS

_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
_VIEWBOX_SEPARATOR = re.compile(r"[\s,]+")
_UNSAFE_IN_STYLE = ("javascript:", "expression(", "@import", "behavior:", "-moz-binding")
# Attributes that name another resource. Kept deliberately short: the animation
# attributes that belong here (``from``, ``to``, ``attributeName``) only appear on
# elements the allowlist already drops, and ``values`` is a list of numbers on
# ``feColorMatrix``, which a reference rule would wrongly strip.
_REFERENCE_ATTRIBUTES = {"href", "src", "base"}


@dataclass(frozen=True)
class SanitizedSvg:
    """What the store keeps: the cleaned document, its box, and the receipt."""

    content: str
    view_box: ViewBox
    report: dict


def sanitize_svg(data: bytes, max_bytes: int) -> SanitizedSvg:
    """Clean an uploaded SVG, or say why it cannot be one."""
    _check_size(data, max_bytes)
    source = _decode(data)
    root = _parse(source)
    view_box = _parse_view_box(root.get("viewBox"))

    removed_elements: Counter[str] = Counter()
    removed_attributes: Counter[str] = Counter()
    _clean_attributes(root, removed_attributes)
    _clean_children(root, 1, removed_elements, removed_attributes)

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    return SanitizedSvg(
        content=ET.tostring(root, encoding="unicode", short_empty_elements=True),
        view_box=view_box,
        report={
            "removed_elements": dict(sorted(removed_elements.items())),
            "removed_attributes": dict(sorted(removed_attributes.items())),
        },
    )


# -- getting to a tree --------------------------------------------------------


def _check_size(data: bytes, max_bytes: int) -> None:
    if len(data) > max_bytes:
        raise SvgTooLarge(
            f"An SVG upload is at most {max_bytes} bytes.",
            evidence={"bytes": len(data), "max_bytes": max_bytes},
        )


def _decode(data: bytes) -> str:
    if not data.strip():
        raise InvalidSvg("The upload is empty.")
    try:
        source = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidSvg("An SVG upload must be UTF-8.") from exc
    lowered = source.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        # Conservative: refused on the raw text, before a parser can expand
        # anything. A drawing that merely contains this wording in a <desc> is
        # collateral, and a rare enough price for not hand-rolling entity limits.
        raise InvalidSvg("DTD and entity declarations are not accepted.")
    return source


def _parse(source: str) -> ET.Element:
    try:
        root = ET.fromstring(source)
    except (ET.ParseError, ValueError) as exc:
        raise InvalidSvg(f"The upload is not well-formed XML: {exc}.") from exc
    namespace, local = _qualified(root.tag)
    if local.lower() != "svg" or namespace not in (None, SVG_NS):
        raise InvalidSvg("The root element must be <svg>.")
    return root


def _parse_view_box(raw: str | None) -> ViewBox:
    """A map without a coordinate space is not a map we can pin anything to.

    Deliberately not synthesized from ``width``/``height``: those are a display
    size, they are frequently absent or in physical units, and guessing here
    would silently invent the space every stored pin is measured against.
    """
    if not raw:
        raise InvalidSvg("The <svg> element must declare a viewBox.")
    parts = [part for part in _VIEWBOX_SEPARATOR.split(raw.strip()) if part]
    if len(parts) != 4:
        raise InvalidSvg("A viewBox is four numbers: min-x, min-y, width, height.")
    try:
        values = [float(part) for part in parts]
    except ValueError as exc:
        raise InvalidSvg("A viewBox is four numbers.") from exc
    if not all(math.isfinite(value) for value in values):
        raise InvalidSvg("A viewBox must be finite.")
    if values[2] <= 0 or values[3] <= 0:
        raise InvalidSvg("A viewBox must have positive width and height.")
    return ViewBox(*values)


# -- pruning ------------------------------------------------------------------


def _clean_children(parent, depth: int, elements: Counter, attributes: Counter) -> None:
    if depth > MAX_DEPTH:
        raise InvalidSvg(f"The drawing nests deeper than {MAX_DEPTH} levels.")
    for child in list(parent):
        namespace, local = _qualified(child.tag)
        if namespace not in (None, SVG_NS) or local.lower() not in _ALLOWED_ELEMENTS:
            parent.remove(child)
            elements[local] += 1
            continue
        _clean_attributes(child, attributes)
        _clean_children(child, depth + 1, elements, attributes)


def _clean_attributes(element, removed: Counter) -> None:
    for key, value in list(element.attrib.items()):
        namespace, local = _qualified(key)
        if namespace not in (None, XLINK_NS, XML_NS) or _unsafe(local, value):
            del element.attrib[key]
            removed[local] += 1


def _unsafe(name: str, value: str) -> bool:
    """Whether an attribute earns removal, judged by name and then by value."""
    lowered = name.lower()
    if lowered.startswith("on"):
        return True
    if lowered == "style":
        return _unsafe_style(value)
    if lowered in _REFERENCE_ATTRIBUTES:
        # Anything that names another resource may only name this document.
        return not value.strip().startswith("#")
    return _points_outward(value)


def _unsafe_style(value: str) -> bool:
    lowered = value.lower()
    if any(token in lowered for token in _UNSAFE_IN_STYLE):
        return True
    return _points_outward(value)


def _points_outward(value: str) -> bool:
    """True if any ``url(...)`` in the value leaves this document."""
    return any(
        not match.group(2).strip().startswith("#") for match in _URL.finditer(value)
    )


def _qualified(name: str) -> tuple[str | None, str]:
    """Split ElementTree's ``{namespace}local`` spelling; namespace may be None."""
    if name.startswith("{") and "}" in name:
        namespace, local = name[1:].split("}", 1)
        return namespace, local
    return None, name
