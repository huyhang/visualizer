"""The goal diagram's layout, exercised from pytest.

``goallayout.js`` decides where every goal box and every dependency edge lands.
It is pure -- a list of goals in, coordinates out -- and it is the only part of
the goals UI that can be *wrong* rather than merely ugly: a row ordered badly
crosses edges that need not cross, and an edge drawn straight through the boxes
between its ends reads as an edge to those boxes.

So this runs it, the same way ``test_graph_js`` runs the story map's layout:
``node`` from the PATH or from the ``nodejs-wheel-binaries`` dev dependency, the
module copied into a tmp dir beside a ``{"type": "module"}`` package.json.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_JS_DIR = Path(__file__).resolve().parents[2] / "src" / "visualizer" / "chronos" / "static" / "js"

_PREAMBLE = """\
import { layoutGoals } from "./goallayout.js";
const INPUT = %s;
const emit = (value) => console.log(JSON.stringify(value));
"""


def _node_binary():
    """node from the PATH, else the one the dev dependency ships, else None."""
    found = shutil.which("node")
    if found:
        return found
    try:
        import nodejs_wheel  # optional: only this module needs it
    except ImportError:
        return None
    exe = "node.exe" if sys.platform == "win32" else "node"
    candidate = Path(nodejs_wheel.__file__).parent / "bin" / exe
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def run_js(tmp_path_factory):
    node = _node_binary()
    if node is None:
        pytest.skip("no node available -- `pip install -e \".[dev]\"` provides one")
    workspace = tmp_path_factory.mktemp("goals-js")
    (workspace / "package.json").write_text('{"type": "module"}')
    shutil.copy(_JS_DIR / "goallayout.js", workspace / "goallayout.js")

    def run(body: str, payload=None):
        script = workspace / "driver.js"
        script.write_text(_PREAMBLE % json.dumps(payload if payload is not None else []) + body)
        done = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60, check=False,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


def goal(gid, depth=0, depends_on=(), name=None):
    return {"id": gid, "name": name or gid, "depth": depth, "depends_on": list(depends_on)}


LAYOUT = "emit(layoutGoals(INPUT));"


# -- rows --------------------------------------------------------------------


def test_a_goal_is_drawn_below_everything_it_rests_on(run_js):
    """The whole message of the diagram: read downward and you read the order
    things have to happen in."""
    goals = [goal("claim"), goal("crown", 1, ["claim"])]
    out = run_js(LAYOUT, goals)
    at = {n["id"]: n for n in out["nodes"]}
    assert at["claim"]["y"] < at["crown"]["y"]
    assert at["claim"]["depth"] == 0 and at["crown"]["depth"] == 1


def test_goals_at_the_same_depth_share_a_row(run_js):
    goals = [goal("a"), goal("b"), goal("c"), goal("needs-all", 1, ["a", "b", "c"])]
    out = run_js(LAYOUT, goals)
    at = {n["id"]: n for n in out["nodes"]}
    assert at["a"]["y"] == at["b"]["y"] == at["c"]["y"]
    assert out["rows"] == 2


def test_a_row_is_ordered_to_sit_under_what_it_rests_on_not_by_name(run_js):
    """`zeta` rests on the left-hand root and `alpha` on the right-hand one.
    By name they would cross; by barycentre they do not."""
    goals = [
        goal("left"), goal("right"),
        goal("zeta", 1, ["left"]), goal("alpha", 1, ["right"]),
    ]
    out = run_js(LAYOUT, goals)
    at = {n["id"]: n for n in out["nodes"]}
    assert at["left"]["x"] < at["right"]["x"]          # roots by name
    assert at["zeta"]["x"] < at["alpha"]["x"]          # ...and their dependents follow
    assert (at["zeta"]["x"] - at["left"]["x"]) == (at["alpha"]["x"] - at["right"]["x"])


def test_the_same_book_lays_out_the_same_way_whatever_order_it_arrives_in(run_js):
    goals = [goal("b"), goal("a"), goal("c", 1, ["a", "b"])]
    forwards = run_js(LAYOUT, goals)
    backwards = run_js(LAYOUT, list(reversed(goals)))
    assert forwards["nodes"] == backwards["nodes"]


def test_rows_are_centred_against_the_widest_one(run_js):
    """One root over three dependents reads as a fan, not as a left margin."""
    goals = [goal("root"), *(goal(f"leaf{i}", 1, ["root"]) for i in range(3))]
    out = run_js(LAYOUT, goals)
    at = {n["id"]: n for n in out["nodes"]}
    leaves = [at[f"leaf{i}"] for i in range(3)]
    span = (min(n["x"] for n in leaves), max(n["x"] + n["width"] for n in leaves))
    root_centre = at["root"]["x"] + at["root"]["width"] / 2
    assert root_centre == pytest.approx((span[0] + span[1]) / 2)


# -- the band of loose goals -------------------------------------------------


def test_goals_with_no_edges_do_not_widen_the_graph(run_js):
    """The reason this exists: most goals rest on nothing and carry nothing, and
    in the graph's first layer they made it as wide as the book is long."""
    graph = [goal("a"), goal("b"), goal("c"), goal("needs-all", 1, ["a", "b", "c"])]
    loose = [goal(f"loose{i}") for i in range(5)]
    joined = run_js(LAYOUT, graph)
    with_loose = run_js(LAYOUT, graph + loose)
    # Five more goals, and the diagram is exactly as wide as it was — they wrap
    # into the three columns the graph already occupies, and go downwards.
    assert with_loose["width"] == joined["width"]
    assert with_loose["height"] > joined["height"]


def test_the_loose_ones_sit_above_the_graph(run_js):
    goals = [goal("claim"), goal("crown", 1, ["claim"]), goal("loose")]
    out = run_js(LAYOUT, goals)
    at = {n["id"]: n for n in out["nodes"]}
    assert at["loose"]["y"] < at["claim"]["y"] < at["crown"]["y"]
    assert at["loose"]["island"] and not at["claim"]["island"]
    assert out["band"] == 1


def test_they_wrap_into_the_width_the_graph_already_takes(run_js):
    """Two connected columns, so the loose ones go two to a line."""
    goals = [
        goal("a"), goal("b"), goal("c", 1, ["a", "b"]),
        *(goal(f"loose{i}") for i in range(4)),
    ]
    out = run_js(LAYOUT, goals)
    rows = {}
    for node in out["nodes"]:
        rows.setdefault(node["y"], []).append(node["id"])
    band = [ids for y, ids in sorted(rows.items()) if all(i.startswith("loose") for i in ids)]
    assert [len(row) for row in band] == [2, 2]
    assert out["band"] == 2


def test_a_book_of_nothing_but_loose_goals_goes_roughly_square(run_js):
    """No graph to borrow a width from, and one very long line would be worse
    than a block."""
    out = run_js(LAYOUT, [goal(f"g{i}") for i in range(9)])
    assert out["rows"] == 3 and out["band"] == 3


def test_a_loose_goal_still_says_it_rests_on_nothing(run_js):
    """Its row in the band is not a depth. Wrapping onto the second line does
    not mean it comes after the first."""
    out = run_js(LAYOUT, [goal(f"g{i}") for i in range(4)])
    assert {n["depth"] for n in out["nodes"]} == {0}


def test_a_goal_whose_only_prerequisite_is_gone_counts_as_loose(run_js):
    """No line will be drawn to it, so it belongs where the other unattached
    goals are — the finding on its card says what happened."""
    out = run_js(LAYOUT, [goal("claim"), goal("crown", 1, ["claim"]), goal("orphan", 0, ["ghost"])])
    at = {n["id"]: n for n in out["nodes"]}
    assert at["orphan"]["island"]
    assert at["orphan"]["y"] < at["claim"]["y"]


def test_the_band_is_set_apart_from_the_graph(run_js):
    """A gap, so the last line of loose goals does not read as the layer
    everything below it depends on."""
    banded = run_js(LAYOUT, [goal("claim"), goal("crown", 1, ["claim"]), goal("loose")])
    at = {n["id"]: n for n in banded["nodes"]}
    band_to_graph = at["claim"]["y"] - at["loose"]["y"]
    layer_to_layer = at["crown"]["y"] - at["claim"]["y"]
    assert band_to_graph > layer_to_layer


# -- edges -------------------------------------------------------------------


def _points(geometry):
    """The coordinate pairs in a path (``x y``) or a polygon (``x,y``)."""
    return [tuple(map(float, re.split(r"[ ,]", pair)))
            for pair in re.findall(r"-?[\d.]+[ ,]-?[\d.]+", geometry)]


def test_an_edge_leaves_the_bottom_of_one_box_and_meets_the_top_of_the_other(run_js):
    out = run_js(LAYOUT, [goal("claim"), goal("crown", 1, ["claim"])])
    at = {n["id"]: n for n in out["nodes"]}
    edge = out["edges"][0]
    start = _points(edge["path"])[0]
    assert start == (at["claim"]["x"] + at["claim"]["width"] / 2,
                     at["claim"]["y"] + at["claim"]["height"])
    # The *arrow's tip* is what lands on the target, not the line's end.
    tip = _points(edge["arrow"])[0]
    assert tip == (at["crown"]["x"] + at["crown"]["width"] / 2, at["crown"]["y"])


# -- the arrowhead -----------------------------------------------------------
#
# A triangle rather than an SVG marker, so it can carry the same class as the
# line it belongs to and cannot be lost to `url(#id)` resolution. That makes its
# geometry this module's problem, and therefore testable.


def test_the_line_stops_short_so_it_cannot_show_through_the_head(run_js):
    out = run_js(LAYOUT, [goal("claim"), goal("crown", 1, ["claim"])])
    at = {n["id"]: n for n in out["nodes"]}
    end = _points(out["edges"][0]["path"])[-1]
    tip = _points(out["edges"][0]["arrow"])[0]
    assert end[1] < tip[1], "the line should end above the tip"
    assert tip[1] - end[1] == pytest.approx(10, abs=0.01)  # one arrow length
    assert at["crown"]["y"] == tip[1]


def test_the_head_is_a_triangle_square_to_the_direction_of_travel(run_js):
    """A straight-down edge gets a level base; the two corners sit either side
    of the line, the arrow length back from the tip."""
    out = run_js(LAYOUT, [goal("claim"), goal("crown", 1, ["claim"])])
    tip, left, right = _points(out["edges"][0]["arrow"])
    assert left[1] == right[1] == tip[1] - 10          # base is level, behind the tip
    assert left[0] == pytest.approx(tip[0] - 3.5)      # half the arrow's width
    assert right[0] == pytest.approx(tip[0] + 3.5)


def test_a_bowed_edge_arrives_at_an_angle_and_its_head_turns_with_it(run_js):
    """The head follows the curve's tangent, not the straight line between the
    boxes -- otherwise a bowed edge lands with its arrow pointing askew."""
    goals = [goal("root"), goal("middle", 1, ["root"]), goal("far", 2, ["root", "middle"])]
    out = run_js(LAYOUT, goals)
    edges = {(e["from"], e["to"]): e for e in out["edges"]}
    tip, left, right = _points(edges[("root", "far")]["arrow"])
    assert left[1] != right[1], "a bowed arrival should not have a level base"
    straight = _points(edges[("middle", "far")]["arrow"])
    assert straight[1][1] == straight[2][1], "the unbowed one should"
    assert tip == straight[0], "both still land on the same box top"


def test_the_head_grows_with_the_reader_text_size(run_js):
    """It is drawn in the same coordinate space as the boxes, so it has to scale
    with them or it shrinks away as the diagram grows."""
    out = run_js("emit(layoutGoals(INPUT, { scale: 2 }));",
                 [goal("claim"), goal("crown", 1, ["claim"])])
    tip, left, _ = _points(out["edges"][0]["arrow"])
    assert tip[1] - left[1] == pytest.approx(20)  # two arrow lengths


def test_an_edge_that_skips_a_row_bows_clear_of_it(run_js):
    """A goal may rest on something two rows up. A straight line would run
    behind the box in between and read as an edge to *that*."""
    goals = [goal("root"), goal("middle", 1, ["root"]), goal("far", 2, ["root", "middle"])]
    out = run_js(LAYOUT, goals)
    edges = {(e["from"], e["to"]): e["path"] for e in out["edges"]}
    long_controls = _points(edges[("root", "far")])[1:3]
    short_controls = _points(edges[("middle", "far")])[1:3]
    straight = _points(edges[("root", "far")])[0][0]
    assert all(abs(c[0] - straight) > 20 for c in long_controls)
    # The one-row edge stays straight: it has nothing to clear.
    assert all(c[0] == _points(edges[("middle", "far")])[0][0] for c in short_controls)


def test_a_dependency_that_is_not_in_the_book_is_left_undrawn(run_js):
    """It is reported as a finding on the goal; an edge to nowhere would be a
    line ending in empty space."""
    out = run_js(LAYOUT, [goal("crown", 0, ["ghost"])])
    assert out["edges"] == []


# -- bad data ----------------------------------------------------------------


def test_a_loop_still_draws_every_goal(run_js):
    """Writes refuse a loop, so this is data that got there sideways -- and a
    diagram that silently dropped a goal would be a worse way to find out."""
    goals = [goal("a", 0, ["b"]), goal("b", 0, ["a"])]
    out = run_js(LAYOUT, goals)
    assert {n["id"] for n in out["nodes"]} == {"a", "b"}
    assert len(out["edges"]) == 2


def test_an_empty_book_lays_out_without_falling_over(run_js):
    out = run_js(LAYOUT, [])
    assert out["nodes"] == [] and out["edges"] == []
    assert out["width"] > 0 and out["height"] > 0
