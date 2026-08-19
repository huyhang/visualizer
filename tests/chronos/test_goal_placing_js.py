"""Where a goal goes on a graph of scenes, exercised from pytest.

``goalplacing.js`` is the one part of putting goals on the visualisations that
can be *wrong* rather than merely ugly. A goal marked on the wrong scene is a
lie about the story; a goal quietly dropped because the view is not showing the
scene that delivers it is a worse one -- a thread pursuing four goals and marking
one reads as a thread with one goal, and nothing on screen says otherwise.

So it is pure -- refs and coverage in, marks and misses out -- and this runs it
the way ``test_goal_layout_js`` runs the diagram's layout: ``node`` from the PATH
or from the ``nodejs-wheel-binaries`` dev dependency, the module copied into a
tmp dir beside a ``{"type": "module"}`` package.json.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_JS_DIR = Path(__file__).resolve().parents[2] / "src" / "visualizer" / "chronos" / "static" / "js"

_PREAMBLE = """\
import {
  ELSEWHERE, MISSING, NO_SCENE, coverageOf, eachAlone, placeGoals, pursuedBy, stripFor,
} from "./goalplacing.js";
const INPUT = %s;
const emit = (value) => console.log(JSON.stringify(value));
// Maps do not survive JSON, and what a test wants to assert on is the mapping.
const marksOf = (placed) => Object.fromEntries(
  [...placed.marks].map(([node, refs]) => [node, refs.map((r) => r.id)]),
);
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
    workspace = tmp_path_factory.mktemp("placing-js")
    (workspace / "package.json").write_text('{"type": "module"}')
    shutil.copy(_JS_DIR / "goalplacing.js", workspace / "goalplacing.js")

    def run(body: str, payload=None):
        script = workspace / "driver.js"
        script.write_text(_PREAMBLE % json.dumps(payload if payload is not None else []) + body)
        done = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60, check=False,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


def ref(gid, at=None, scene=None, when=None, missing=False):
    """A goal ref in the shape the server sends one."""
    if missing:
        return {"id": gid, "title": gid, "missing": True}
    return {
        "id": gid,
        "title": gid.title(),
        "missing": False,
        "achieved_at": at,
        "achieved_scene": None if at is None else {
            "id": at, "title": scene or at, "when": when,
        },
    }


# -- marks --------------------------------------------------------------------


def test_a_goal_is_marked_on_the_scene_that_delivers_it(run_js):
    got = run_js(
        "emit(marksOf(placeGoals(INPUT, eachAlone(['s1', 's2', 's3']))));",
        [ref("crown", at="s2")],
    )
    assert got == {"s2": ["crown"]}


def test_two_goals_landing_on_one_scene_both_ride_on_it(run_js):
    """A scene can pay off more than one thing, and the second must not evict
    the first -- a Map keyed by node with one value would do exactly that."""
    got = run_js(
        "emit(marksOf(placeGoals(INPUT, eachAlone(['s1']))));",
        [ref("crown", at="s1"), ref("peace", at="s1")],
    )
    assert got == {"s1": ["crown", "peace"]}


def test_nothing_is_marked_on_a_scene_no_goal_names(run_js):
    got = run_js(
        "emit(marksOf(placeGoals(INPUT, eachAlone(['s1', 's2']))));",
        [ref("crown", at="s1")],
    )
    assert got == {"s1": ["crown"]}


# -- the three ways to be unplaced ---------------------------------------------


def test_a_goal_with_no_scene_says_so_rather_than_vanishing(run_js):
    got = run_js(
        "emit(placeGoals(INPUT, eachAlone(['s1'])).unplaced);",
        [ref("crown")],
    )
    assert got == [{
        "id": "crown", "title": "Crown", "reason": "no-scene", "note": "no scene yet",
    }]


def test_a_goal_delivered_off_this_view_names_where_it_landed(run_js):
    """The interesting case: a thread pursues it, another thread delivers it.
    Marking nothing would read as "this goal is going nowhere", which is the
    opposite of true."""
    got = run_js(
        "emit(placeGoals(INPUT, eachAlone(['s1'])).unplaced);",
        [ref("crown", at="s9", scene="The Coronation", when="Year 3, Moon 4")],
    )
    assert got[0]["reason"] == "elsewhere"
    assert got[0]["note"] == "delivered at The Coronation · Year 3, Moon 4"


def test_an_undated_landing_scene_is_named_without_an_empty_date(run_js):
    got = run_js(
        "emit(placeGoals(INPUT, eachAlone(['s1'])).unplaced);",
        [ref("crown", at="s9", scene="The Coronation", when=None)],
    )
    assert got[0]["note"] == "delivered at The Coronation"


def test_a_dangling_goal_id_is_said_plainly(run_js):
    """It cannot be opened, so the strip must not offer to -- and a finding
    elsewhere already explains how a book gets into that state."""
    got = run_js(
        "emit(placeGoals(INPUT, eachAlone(['s1'])).unplaced);",
        [ref("ghost", missing=True)],
    )
    assert got == [{
        "id": "ghost", "title": "ghost", "reason": "missing",
        "note": "no longer in this book",
    }]


def test_a_goal_whose_scene_left_the_book_is_not_called_elsewhere(run_js):
    """`achieved_at` set with no `achieved_scene` means the scene is gone, not
    that it is on a thread we are not showing."""
    got = run_js(
        "emit(placeGoals(INPUT, eachAlone(['s1'])).unplaced);",
        [{"id": "crown", "title": "Crown", "missing": False,
          "achieved_at": "s9", "achieved_scene": None}],
    )
    assert got[0]["note"] == "delivered by a scene that is no longer in the book"


def test_every_goal_is_either_marked_or_named(run_js):
    """The invariant the strip exists to hold: nothing falls off the page."""
    got = run_js(
        """
        const placed = placeGoals(INPUT, eachAlone(['s1', 's2']));
        const marked = [...placed.marks.values()].flat().map((r) => r.id);
        emit({ marked, missed: placed.unplaced.map((g) => g.id) });
        """,
        [ref("a", at="s1"), ref("b", at="s2"), ref("c"), ref("d", at="elsewhere"),
         ref("e", missing=True)],
    )
    assert sorted(got["marked"] + got["missed"]) == ["a", "b", "c", "d", "e"]


# -- folded runs ---------------------------------------------------------------


def test_a_goal_inside_a_folded_run_is_marked_on_the_band(run_js):
    """Folding a stretch of solitary scenes must not fold away the fact that one
    of them pays off a goal -- that is precisely the row worth unfolding."""
    got = run_js(
        """
        const nodes = [
          { id: "junction" },
          { id: "~run:aldric:s4", is_band: true, events: ["s4", "s5", "s6"] },
        ];
        emit(marksOf(placeGoals(INPUT, coverageOf(nodes))));
        """,
        [ref("crown", at="s5")],
    )
    assert got == {"~run:aldric:s4": ["crown"]}


def test_unfolding_moves_the_mark_from_the_band_to_the_scene(run_js):
    got = run_js(
        """
        const folded = [{ id: "~run:a:s4", is_band: true, events: ["s4", "s5"] }];
        const open = [{ id: "s4" }, { id: "s5" }];
        emit({
          folded: marksOf(placeGoals(INPUT, coverageOf(folded))),
          open: marksOf(placeGoals(INPUT, coverageOf(open))),
        });
        """,
        [ref("crown", at="s5")],
    )
    assert got["folded"] == {"~run:a:s4": ["crown"]}
    assert got["open"] == {"s5": ["crown"]}


# -- what the strip narrows to -------------------------------------------------


def test_the_strip_names_only_what_the_shown_threads_pursue(run_js):
    """Otherwise ticking fewer threads would make the strip *longer*, which is
    exactly backwards: it would fill with goals belonging to threads the writer
    deliberately hid."""
    got = run_js(
        """
        const lanes = [{ id: "aldric", goals: ["crown"] }];
        const placed = placeGoals(INPUT, eachAlone(["s1"]));
        emit({
          all: placed.unplaced.map((g) => g.id),
          strip: stripFor(placed, lanes).map((g) => g.id),
        });
        """,
        [ref("crown"), ref("someone-elses-goal")],
    )
    assert got["all"] == ["crown", "someone-elses-goal"]
    assert got["strip"] == ["crown"]


def test_a_goal_no_shown_thread_pursues_is_still_marked_where_it_lands(run_js):
    """The strip narrows; the marks do not. A scene on screen that delivers a
    goal is worth seeing whoever is pursuing it."""
    got = run_js(
        """
        const lanes = [{ id: "aldric", goals: [] }];
        const placed = placeGoals(INPUT, eachAlone(["s1"]));
        emit({ marks: marksOf(placed), strip: stripFor(placed, lanes).length });
        """,
        [ref("crown", at="s1")],
    )
    assert got == {"marks": {"s1": ["crown"]}, "strip": 0}


def test_threads_pursuing_the_same_goal_name_it_once(run_js):
    got = run_js(
        """
        emit([...pursuedBy([
          { id: "a", goals: ["crown", "peace"] },
          { id: "b", goals: ["crown"] },
          { id: "c" },
        ])]);
        """,
    )
    assert sorted(got) == ["crown", "peace"]


# -- degenerate input ----------------------------------------------------------


@pytest.mark.parametrize("refs", [None, []])
def test_a_book_with_no_goals_places_nothing_and_does_not_throw(run_js, refs):
    got = run_js(
        "emit(placeGoals(INPUT, eachAlone(['s1'])).unplaced.length);", refs,
    )
    assert got == 0


def test_a_view_showing_no_scenes_puts_every_goal_in_the_strip(run_js):
    got = run_js(
        "emit(placeGoals(INPUT, eachAlone([])).unplaced.map((g) => g.reason));",
        [ref("crown", at="s1", scene="A Scene")],
    )
    assert got == ["elsewhere"]
