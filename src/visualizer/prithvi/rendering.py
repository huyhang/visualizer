"""Drawing pins onto a stored map, purely.

The API is the product, so this exists for one reason: a URL you can open. It
takes the sanitized SVG and the pins the caller is allowed to see, and returns a
new SVG with a pin layer appended. No Flask, no store, no permissions -- the
caller has already decided which pins these are.

Two details are deliberate rather than decorative. Marker geometry is derived
from the ``viewBox`` rather than fixed, because a 100-unit town plan and a
4000-unit continent are the same picture at different scales and a constant
radius would be invisible on one and enormous on the other. And strokes carry
``vector-effect="non-scaling-stroke"``, because everything in an SVG scales with
the viewport except the thing you want to stay legible.
"""

from urllib.parse import quote
from xml.etree import ElementTree as ET

from .models import ViewBox
from .svg import SVG_NS

LAYER_ID = "prithvi-pins"

_MARKER_RADIUS = 0.014  # of the shorter viewBox side
_LABEL_SIZE = 1.8  # of the marker radius
_LABEL_OFFSET = 1.45  # of the marker radius
_INK = "#2b2118"
_PIN_FILL = "#b42318"
_PAPER = "#fff7df"


def render_pins(svg: str, view_box: ViewBox, pins: list[dict], akasha_url: str) -> str:
    """Return ``svg`` with a labelled, linked marker for each pin."""
    root = ET.fromstring(svg)
    layer = ET.SubElement(root, _tag("g"), {"id": LAYER_ID, "aria-label": "Map pins"})
    radius = view_box.smaller_side * _MARKER_RADIUS
    for pin in pins:
        _draw_pin(layer, pin, radius, akasha_url)
    ET.register_namespace("", SVG_NS)
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)


def _draw_pin(layer, pin: dict, radius: float, akasha_url: str) -> None:
    article = pin["article"]
    title = article.get("title") or article["id"]
    parent = _anchor(layer, article, title, akasha_url)
    marker = ET.SubElement(
        parent,
        _tag("g"),
        {
            "class": "prithvi-pin",
            "data-collection": article["collection"],
            "data-article": article["id"],
        },
    )
    ET.SubElement(marker, _tag("title")).text = title
    _draw_marker(marker, pin["position"], radius)
    _draw_label(marker, pin["position"], radius, title)


def _anchor(layer, article: dict, title: str, akasha_url: str):
    """Wrap a pin in a link to its article -- unless the article is gone."""
    if article.get("status") != "available":
        return layer
    return ET.SubElement(
        layer,
        _tag("a"),
        {
            "href": _article_url(akasha_url, article),
            "target": "_top",
            "aria-label": f"Open {title} in Akasha",
        },
    )


def _draw_marker(marker, position: dict, radius: float) -> None:
    ET.SubElement(
        marker,
        _tag("circle"),
        {
            "cx": _number(position["x"]),
            "cy": _number(position["y"]),
            "r": _number(radius),
            "fill": _PIN_FILL,
            "stroke": _PAPER,
            "stroke-width": _number(radius * 0.28),
            "vector-effect": "non-scaling-stroke",
        },
    )
    ET.SubElement(
        marker,
        _tag("circle"),
        {
            "cx": _number(position["x"]),
            "cy": _number(position["y"]),
            "r": _number(radius * 0.28),
            "fill": _PAPER,
        },
    )


def _draw_label(marker, position: dict, radius: float, title: str) -> None:
    """A label with its own outline, so it stays readable over any terrain."""
    size = radius * _LABEL_SIZE
    label = ET.SubElement(
        marker,
        _tag("text"),
        {
            "x": _number(position["x"] + radius * _LABEL_OFFSET),
            "y": _number(position["y"] - radius * _LABEL_OFFSET * 0.25),
            "font-family": "serif",
            "font-size": _number(size),
            "font-weight": "700",
            "fill": _INK,
            "stroke": _PAPER,
            "stroke-width": _number(size * 0.16),
            "paint-order": "stroke",
        },
    )
    label.text = title


def _article_url(base: str, article: dict) -> str:
    """Akasha's browser route for one article: ``#/<db>/<collection>/<id>``."""
    parts = (article["database"], article["collection"], article["id"])
    return f"{base.rstrip('/')}/#/{'/'.join(quote(part, safe='') for part in parts)}"


def _tag(local: str) -> str:
    return f"{{{SVG_NS}}}{local}"


def _number(value: float) -> str:
    return f"{value:.6g}"
