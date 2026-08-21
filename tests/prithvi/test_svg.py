"""What the sanitizer keeps, what it removes, and what it refuses outright."""

import pytest

from visualizer.prithvi.errors import InvalidSvg, SvgTooLarge
from visualizer.prithvi.svg import MAX_DEPTH, sanitize_svg

CAP = 100_000


def clean(markup: str):
    return sanitize_svg(markup.encode(), CAP)


def wrap(inner: str, extra: str = "") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10"{extra}>'
        f"{inner}</svg>"
    )


# -- what has to go -----------------------------------------------------------


@pytest.mark.parametrize(
    "name,inner",
    [
        ("script", "<script>alert(1)</script>"),
        ("style element", "<style>rect{fill:red}</style>"),
        ("foreignObject", "<foreignObject><b>hi</b></foreignObject>"),
        ("animation", '<animate attributeName="x" to="5"/>'),
        # <set> can retarget an ancestor's href at a javascript: URL after load,
        # which is why animation elements go even though they cannot script
        # directly.
        ("set", '<set attributeName="href" to="javascript:alert(1)"/>'),
        ("image", '<image href="https://example.test/x.png"/>'),
        ("feImage", '<filter><feImage href="https://example.test/x"/></filter>'),
    ],
)
def test_active_and_remote_elements_are_removed(name, inner):
    assert "javascript" not in clean(wrap(inner)).content
    assert "example.test" not in clean(wrap(inner)).content
    assert clean(wrap(inner)).report["removed_elements"], name


def test_event_handlers_and_scripting_urls_are_removed():
    result = clean(wrap('<a href="javascript:alert(1)"><rect onclick="bad()"/></a>'))

    assert "javascript" not in result.content
    assert "onclick" not in result.content
    assert result.report["removed_attributes"] == {"href": 1, "onclick": 1}


def test_a_namespaced_href_is_not_a_hiding_place():
    """``xlink:href`` is the same attribute wearing a namespace.

    Matching attribute names as plain strings misses it, because ElementTree
    spells it ``{http://www.w3.org/1999/xlink}href``.
    """
    result = clean(wrap('<a xlink:href="javascript:alert(1)"><rect/></a>'))

    assert "javascript" not in result.content
    assert result.report["removed_attributes"] == {"href": 1}


def test_a_scripting_url_inside_a_style_takes_the_style_with_it():
    result = clean(wrap('<rect style="fill:url(javascript:alert(1))"/>'))

    assert "javascript" not in result.content
    assert result.report["removed_attributes"] == {"style": 1}


def test_external_references_are_removed_wherever_they_hide():
    result = clean(
        wrap(
            '<rect fill="url(https://example.test/p.svg#paint)" '
            "style=\"background:url('http://example.test/x')\"/>"
        )
    )

    assert "example.test" not in result.content
    assert result.report["removed_attributes"] == {"fill": 1, "style": 1}


def test_foreign_namespaces_are_dropped_from_elements_and_attributes():
    result = clean(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'viewBox="0 0 10 10"><rect inkscape:label="layer"/>'
        "<inkscape:grid/></svg>"
    )

    assert "inkscape" not in result.content
    assert result.report["removed_elements"] == {"grid": 1}
    assert result.report["removed_attributes"] == {"label": 1}


# -- what has to stay ---------------------------------------------------------


def test_ordinary_drawing_survives_untouched():
    result = clean(
        wrap(
            '<g id="land"><path d="M0 0 L10 10" fill="#e8d9ad"/>'
            '<circle cx="5" cy="5" r="1" style="fill:#b42318;stroke:none"/>'
            '<text x="1" y="2">Emberport</text></g>'
        )
    )

    assert result.report == {"removed_elements": {}, "removed_attributes": {}}
    assert "Emberport" in result.content
    assert "fill:#b42318" in result.content


def test_filter_primitives_survive_because_hill_shading_needs_them():
    """Terrain shading is a blurred alpha channel lit from one side.

    Dropping filters as "exotic" would quietly flatten every relief map this
    service exists to hold, so the allowlist names the primitives instead.
    """
    result = clean(
        wrap(
            '<defs><filter id="hills">'
            '<feGaussianBlur in="SourceAlpha" stdDeviation="9" result="height"/>'
            '<feDiffuseLighting in="height" surfaceScale="13" '
            'lighting-color="#e6d9bd"><feDistantLight azimuth="315" '
            'elevation="40"/></feDiffuseLighting>'
            '<feComposite in2="SourceAlpha" operator="in"/>'
            "</filter></defs>"
            '<ellipse cx="5" cy="5" rx="2" ry="1" filter="url(#hills)"/>'
        )
    )

    assert result.report == {"removed_elements": {}, "removed_attributes": {}}
    assert "feDiffuseLighting" in result.content
    assert 'filter="url(#hills)"' in result.content


def test_a_same_document_reference_is_kept():
    result = clean(wrap('<use href="#land"/><rect fill="url(#grad)"/>'))

    assert result.report["removed_attributes"] == {}
    assert 'href="#land"' in result.content


# -- what is not an SVG at all ------------------------------------------------


@pytest.mark.parametrize(
    "name,body",
    [
        ("not svg", b"<html><body/></html>"),
        ("no viewBox", b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
        ("empty box", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 5"/>'),
        ("three numbers", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 5"/>'),
        ("not numbers", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="a b c d"/>'),
        ("not finite", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 nan 5"/>'),
        ("malformed", b'<svg viewBox="0 0 1 1"><rect>'),
        ("empty", b"   "),
        ("doctype", b'<!DOCTYPE svg><svg viewBox="0 0 1 1"/>'),
        ("entity", b'<!ENTITY x "y"><svg viewBox="0 0 1 1"/>'),
        ("not utf-8", '<svg viewBox="0 0 1 1"/>'.encode("utf-16")),
    ],
)
def test_unusable_uploads_are_refused(name, body):
    with pytest.raises(InvalidSvg):
        sanitize_svg(body, CAP)


def test_a_width_and_height_do_not_stand_in_for_a_viewbox():
    """A display size is not a coordinate space.

    Synthesizing one would invent the units every stored pin is measured in,
    and the invention would only surface when someone's pins were all wrong.
    """
    with pytest.raises(InvalidSvg):
        clean('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"/>')


def test_deep_nesting_is_refused():
    nested = "<g>" * (MAX_DEPTH + 2) + "</g>" * (MAX_DEPTH + 2)
    with pytest.raises(InvalidSvg):
        clean(wrap(nested))


def test_the_size_cap_is_enforced_on_bytes():
    with pytest.raises(SvgTooLarge) as raised:
        sanitize_svg(b"<svg/>" * 100, 50)
    assert raised.value.evidence["max_bytes"] == 50


# -- the asset we ship --------------------------------------------------------


def test_the_demo_map_is_accepted_and_holds_the_pins_the_seed_places():
    """Guards ``docker/``: the drawing and the seed's coordinates go together.

    An edit to either that pulls them apart would otherwise only surface as a
    demo that half-works, on someone else's machine.
    """
    from pathlib import Path

    from visualizer.prithvi.models import Position

    root = Path(__file__).resolve().parents[2]
    result = sanitize_svg((root / "docker" / "ember_pact_map.svg").read_bytes(), CAP)

    assert result.report == {"removed_elements": {}, "removed_attributes": {}}
    assert result.view_box.to_list() == [0.0, 0.0, 1200.0, 720.0]
    for x, y in ((355, 215), (540, 470), (648, 568)):
        assert result.view_box.contains(Position(x, y))
