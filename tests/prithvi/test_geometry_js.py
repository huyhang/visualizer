"""The map page's pure browser modules, run under node from pytest.

``coordinates``, ``zoom`` and ``draft`` hold the only parts of this UI that can
be *wrong* rather than merely ugly: where a click lands, how big the drawing is,
and which writes a Save must issue. They take numbers and return numbers, so
they are tested the same way the story map's layout is -- node from the PATH or
from the ``nodejs-wheel-binaries`` dev dependency, the modules copied into a tmp
dir beside a ``{"type": "module"}`` package.json.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_JS = (
    Path(__file__).resolve().parents[2]
    / "src" / "visualizer" / "prithvi" / "static" / "js"
)
_MODULES = ("coordinates.js", "zoom.js", "draft.js")

_PREAMBLE = """\
import { clientPoint, insideViewBox, transformPoint } from "./coordinates.js";
import {
  anchoredScroll, boxForZoom, clampZoom, fitBox, MAX_ZOOM, MIN_ZOOM, scrollRatio,
  zoomFromWheel, ZOOM_STEP,
} from "./zoom.js";
import {
  changeCount, clonePins, movePin, pinChanges, pinKey, placePin, removePin, samePin,
} from "./draft.js";
"""


def _node():
    found = shutil.which("node")
    if found:
        return found
    try:
        import nodejs_wheel  # optional: only these tests need it
    except ImportError:
        return None
    binary = "node.exe" if sys.platform == "win32" else "node"
    candidate = Path(nodejs_wheel.__file__).parent / "bin" / binary
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def run_js(tmp_path_factory):
    node = _node()
    if node is None:
        pytest.skip('no node available -- `pip install -e ".[dev]"` provides one')
    workspace = tmp_path_factory.mktemp("prithvi-geometry")
    (workspace / "package.json").write_text('{"type":"module"}')
    for name in _MODULES:
        shutil.copy(_JS / name, workspace / name)

    def run(expression):
        script = workspace / "driver.js"
        script.write_text(f"{_PREAMBLE}console.log(JSON.stringify({expression}));\n")
        done = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60, check=False
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


# -- coordinates ------------------------------------------------------------------


def test_screen_points_project_through_the_inverse_matrix(run_js):
    assert run_js("transformPoint(12, 8, {a: 2, b: 0, c: 0, d: 3, e: -4, f: 5})") == {
        "x": 20,
        "y": 29,
    }


def test_a_drawing_with_no_matrix_yields_no_point(run_js):
    assert run_js("clientPoint({getScreenCTM: () => null}, 5, 5)") is None


def test_the_viewbox_edges_are_valid_locations(run_js):
    box = "[10, 20, 100, 50]"
    assert run_js(
        f"[insideViewBox({{x: 10, y: 20}}, {box}),"
        f" insideViewBox({{x: 110, y: 70}}, {box}),"
        f" insideViewBox({{x: 9.9, y: 20}}, {box}),"
        f" insideViewBox({{x: 10, y: 70.1}}, {box}),"
        f" insideViewBox(null, {box}),"
        "  insideViewBox({x: 10, y: 20}, null)]"
    ) == [True, True, False, False, False, False]


# -- zoom -------------------------------------------------------------------------


def test_the_drawing_is_fitted_to_the_maps_own_aspect_ratio(run_js):
    """No letterboxing: the element and the picture are the same rectangle.

    Sizing the element to the *container's* proportions instead leaves dead
    space inside it that scales up with every zoom step.
    """
    wide = run_js("fitBox({width: 846, height: 757}, [0, 0, 1200, 720])")
    assert wide["width"] == 846
    assert wide["height"] == pytest.approx(846 * 720 / 1200)

    tall = run_js("fitBox({width: 900, height: 300}, [0, 0, 100, 200])")
    assert tall["height"] == 300
    assert tall["width"] == pytest.approx(150)


@pytest.mark.parametrize("degenerate", ["[0, 0, 0, 720]", "[0, 0, 1200, 0]", "null"])
def test_a_map_with_no_area_fits_to_nothing_rather_than_dividing_by_zero(
    run_js, degenerate
):
    assert run_js(f"fitBox({{width: 800, height: 600}}, {degenerate})") == {
        "width": 0,
        "height": 0,
    }


def test_zoom_is_clamped_to_its_advertised_range(run_js):
    assert run_js(
        "[clampZoom(0.01), clampZoom(99), clampZoom(NaN), MIN_ZOOM, MAX_ZOOM]"
    ) == [
        0.5,
        4,
        1,
        0.5,
        4,
    ]


def test_a_zoom_cycle_returns_to_exactly_where_it_started(run_js):
    """The regression this module exists for.

    Written the tempting way -- ``box = measured * zoom``, where ``measured`` is
    the element you are about to resize -- the height becomes a running product
    of every factor ever applied: 757 -> 946 -> 1419 -> 2483 -> 4966, and
    zooming *back out* makes it worse because 1.75 and 1.5 are still > 1. Reset
    then multiplies by 1.0 and changes nothing, so there is no way back.

    ``boxForZoom`` takes the fit as an argument instead, so the box at any zoom
    depends only on that zoom. Walking the same in-and-out sequence has to land
    back on the opening size, to the pixel.
    """
    result = run_js(
        """(() => {
          const fit = fitBox({width: 846, height: 757}, [0, 0, 1200, 720]);
          const walk = [1, 1.25, 1.5, 1.75, 2, 1.75, 1.5, 1.25, 1];
          const boxes = walk.map((z) => boxForZoom(fit, z));
          // What the same walk does when the base is the last rendered size
          // instead of the fit -- the shape of the bug this guards against.
          let compounding = fit.height;
          for (const z of walk) compounding = compounding * z;
          return {
            first: boxes[0],
            peak: boxes[4],
            last: boxes[boxes.length - 1],
            heights: boxes.map((b) => Math.round(b.height)),
            compounding: Math.round(compounding),
          };
        })()"""
    )
    assert result["last"] == result["first"]
    assert result["peak"]["height"] == pytest.approx(result["first"]["height"] * 2)
    # Symmetric, and bounded by twice the fit -- never a runaway.
    assert result["heights"] == [508, 635, 761, 888, 1015, 888, 761, 635, 508]
    # The same nine steps, each sized from the previous render instead of from
    # the fit: the box ends more than twenty times too tall, and because the
    # last step multiplies by 1.0, Reset cannot bring it back.
    assert result["compounding"] > result["last"]["height"] * 20


def test_the_box_at_a_zoom_does_not_depend_on_how_you_got_there(run_js):
    assert run_js(
        """(() => {
          const fit = fitBox({width: 846, height: 757}, [0, 0, 1200, 720]);
          const direct = boxForZoom(fit, 2);
          [0.5, 4, 1, 3].forEach((z) => boxForZoom(fit, z));
          const after = boxForZoom(fit, 2);
          return direct.width === after.width && direct.height === after.height;
        })()"""
    ) is True


def test_a_box_never_collapses_to_nothing(run_js):
    assert run_js("boxForZoom({width: 0, height: 0}, 1)") == {"width": 1, "height": 1}


def test_the_wheel_zooms_in_when_scrolled_up_and_stays_in_range(run_js):
    assert run_js(
        "[zoomFromWheel(1, -100) > 1, zoomFromWheel(1, 100) < 1,"
        " zoomFromWheel(4, -10000), zoomFromWheel(0.5, 10000)]"
    ) == [True, True, 4, 0.5]


def test_scrolling_keeps_the_anchored_point_under_the_pointer(run_js):
    assert run_js(
        "[scrollRatio(0, 400, 800), scrollRatio(0, 0, 0),"
        " anchoredScroll(0.5, 1600, 400), anchoredScroll(0.1, 100, 400)]"
    ) == [0.5, 0, 400, 0]


def test_the_zoom_step_divides_the_range_into_whole_stops(run_js):
    assert run_js("[(MAX_ZOOM - MIN_ZOOM) % ZOOM_STEP, ZOOM_STEP]") == [0, 0.25]


# -- the staged edit ---------------------------------------------------------------

_SAVED = (
    "[{world: 'w', map: 'm', article: {collection: 'places', id: 'a'},"
    " position: {x: 1, y: 2}, rev: 3}]"
)
_NEW = "{collection: 'places', id: 'b', title: 'B'}"


def test_pins_are_keyed_on_the_pair_the_api_keys_on(run_js):
    assert run_js(
        "pinKey({article: {collection: 'a b', id: 'c'}})"
        " === pinKey({article: {collection: 'a', id: 'b c'}})"
    ) is False


def test_a_move_and_a_placement_are_one_diff(run_js):
    assert run_js(
        f"""(() => {{
          const saved = {_SAVED};
          let draft = movePin(saved, saved[0], {{x: 4, y: 5}});
          draft = placePin(draft, saved,
            {{world: 'w', map: 'm', article: {_NEW}, position: {{x: 6, y: 7}}}});
          const changes = pinChanges(saved, draft);
          return {{
            count: changeCount(saved, draft),
            moved: changes.moved.map((p) => p.article.id),
            created: changes.created.map((p) => p.article.id),
            deleted: changes.deleted.length,
          }};
        }})()"""
    ) == {"count": 2, "moved": ["a"], "created": ["b"], "deleted": 0}


def test_placing_and_then_removing_leaves_nothing_to_save(run_js):
    assert run_js(
        f"""(() => {{
          let draft = placePin([], [],
            {{world: 'w', map: 'm', article: {_NEW}, position: {{x: 6, y: 7}}}});
          draft = removePin(draft, draft[0]);
          return changeCount([], draft);
        }})()"""
    ) == 0


def test_removing_a_saved_pin_is_staged_as_a_delete(run_js):
    assert run_js(
        f"""(() => {{
          const saved = {_SAVED};
          const draft = removePin(saved, saved[0]);
          return {{
            count: changeCount(saved, draft),
            deleted: pinChanges(saved, draft).deleted.map((p) => p.article.id),
          }};
        }})()"""
    ) == {"count": 1, "deleted": ["a"]}


def test_re_placing_a_removed_pin_is_a_move_and_keeps_its_revision(run_js):
    """It still exists on the server, so Save must PUT it, not POST it.

    A create would collide with the row that is still there. The diff works
    this out from key membership, which is why "take it off, put it back
    somewhere else" needs no special case anywhere in the UI.
    """
    assert run_js(
        f"""(() => {{
          const saved = {_SAVED};
          let draft = removePin(saved, saved[0]);
          draft = placePin(draft, saved, {{
            world: 'w', map: 'm',
            article: {{collection: 'places', id: 'a'}}, position: {{x: 9, y: 9}},
          }});
          const changes = pinChanges(saved, draft);
          return {{
            created: changes.created.length,
            moved: changes.moved.map((p) => ({{id: p.article.id, rev: p.rev}})),
          }};
        }})()"""
    ) == {"created": 0, "moved": [{"id": "a", "rev": 3}]}


def test_re_placing_a_pin_at_the_very_same_spot_is_not_a_change(run_js):
    assert run_js(
        f"""(() => {{
          const saved = {_SAVED};
          let draft = removePin(saved, saved[0]);
          draft = placePin(draft, saved, {{
            world: 'w', map: 'm',
            article: {{collection: 'places', id: 'a'}}, position: {{x: 1, y: 2}},
          }});
          return changeCount(saved, draft);
        }})()"""
    ) == 0


def test_a_new_pin_carries_no_revision_which_is_what_marks_it_a_create(run_js):
    assert run_js(
        f"""(() => {{
          const draft = placePin([], [],
            {{world: 'w', map: 'm', article: {_NEW}, position: {{x: 6, y: 7}}}});
          return {{rev: draft[0].rev, world: draft[0].article.database}};
        }})()"""
    ) == {"rev": None, "world": "w"}


def test_placing_an_article_already_pinned_changes_nothing(run_js):
    assert run_js(
        f"""(() => {{
          const saved = {_SAVED};
          const draft = placePin(saved, saved, {{
            world: 'w', map: 'm',
            article: {{collection: 'places', id: 'a'}}, position: {{x: 8, y: 8}},
          }});
          return changeCount(saved, draft);
        }})()"""
    ) == 0


def test_staging_never_mutates_what_the_server_told_us(run_js):
    assert run_js(
        f"""(() => {{
          const saved = {_SAVED};
          const copy = clonePins(saved);
          movePin(saved, saved[0], {{x: 99, y: 99}});
          removePin(saved, saved[0]);
          return saved.length === 1
            && saved[0].position.x === copy[0].position.x
            && saved[0] !== copy[0];
        }})()"""
    ) is True


def test_two_pins_are_the_same_pin_by_address_not_by_identity(run_js):
    assert run_js(
        "[samePin({article: {collection: 'p', id: 'a'}},"
        "         {article: {collection: 'p', id: 'a'}}),"
        " samePin({article: {collection: 'p', id: 'a'}}, null)]"
    ) == [True, False]
