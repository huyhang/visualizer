"""The story map's pure browser logic, exercised from pytest.

The rest of this suite checks the SPA's *wiring* (test_ui_assets.py) and leaves
the browser code alone, which is the right trade for code that mostly moves DOM
nodes around. Three modules are not that. ``subgraph.js`` decides which threads a
map contains, ``collapse.js`` decides how much of them is drawn, and
``layout.js`` decides where every node, edge and row ends up -- all three are
pure functions over a plain ``/graph`` payload, all three are load-bearing, and
none of them is visible to a Python test that never runs JavaScript.

So this one runs it. ``node`` comes from the ``nodejs-wheel-binaries`` dev
dependency (see pyproject.toml), or from the PATH if the machine already has
one; without either, the module skips with the fix in the message rather than
failing. The modules are copied into a tmp dir beside a ``{"type": "module"}``
package.json, because node reads a bare ``.js`` file as CommonJS and these are ES
modules -- nothing is written into the served static tree.
"""

import json
import shutil
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest

_JS_DIR = Path(__file__).resolve().parents[2] / "src" / "visualizer" / "chronos" / "static" / "js"
# layout.js imports timeaxis.js for the calendar period grouping.
_MODULES = ("layout.js", "subgraph.js", "collapse.js", "timeaxis.js",
            "storygraph.js", "dom.js",
            # storymap.js and everything it reaches, for `remountDeps`. It
            # imports cleanly under node -- nothing in the graph touches the DOM
            # at module scope -- so the helper can be exercised directly.
            "storymap.js", "api.js", "calendarview.js", "cards.js", "findings.js",
            "focus.js", "fontscale.js", "peek.js", "entities.js", "picker.js",
            "paging.js", "table.js",
            # Goals reach the map two ways: the peek panel a mark opens
            # (cards.js -> goalcard.js), and where the marks go (goalplacing.js).
            "goalcard.js", "goalplacing.js")

# Enough of a DOM for the renderer to build against, and no more. Deliberately
# unforgiving: anything storygraph.js reaches for that is not here throws, which
# is the point -- a permissive stub would wave a typo through.
_FAKE_DOM = r"""
const node = (tag, ns) => ({
  tag, ns, attrs: {}, children: [], listeners: {}, dataset: {},
  className: "", textContent: "", style: {},
  appendChild(child) { this.children.push(child); return child; },
  setAttribute(key, value) { this.attrs[key] = String(value); },
  addEventListener(kind, fn) { (this.listeners[kind] ||= []).push(fn); },
});
globalThis.document = {
  createElement: (tag) => node(tag, null),
  createElementNS: (ns, tag) => node(tag, ns),
  createTextNode: (value) => ({ tag: "#text", textContent: value, children: [] }),
};

// Walk a built tree. `cls` matches one class out of the space-separated list the
// way a selector would, so "sg-row" finds "sg-row is-band" too. HTML and SVG
// carry it differently -- dom.js sets `className` on the one and a `class`
// attribute on the other -- and a real selector would not care, so nor does this.
const classesOf = (el) =>
  `${el.className || ""} ${(el.attrs && el.attrs.class) || ""}`.split(" ");
export function find(root, cls, out = []) {
  if (classesOf(root).includes(cls)) out.push(root);
  (root.children || []).forEach((child) => find(child, cls, out));
  return out;
}
export function text(root) {
  if (root.textContent) return root.textContent;
  return (root.children || []).map(text).join(" ").trim();
}
const event = (extra) => ({ stopPropagation() {}, preventDefault() {}, ...extra });
// `target` is the element clicked, as a real event carries it: a row delegates
// its toggle to the whole line and tells its own blank space apart from the
// controls sitting on it by comparing against it.
export const click = (el) => (el.listeners.click || []).forEach((fn) => fn(event({ target: el })));
export const press = (el, key) =>
  (el.listeners.keydown || []).forEach((fn) => fn(event({ key })));
// `is-band` marks both a folded row and the hollow dot beside it, so a test that
// means one of them has to say which.
export const hasClass = (cls) => (el) => classesOf(el).includes(cls);
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


_PREAMBLE = """\
import { applyPeriodGrouping, geometry, layoutGraph, orderLanes } from "./layout.js";
import { connectedTo, restrictTo } from "./subgraph.js";
import { collapseRuns } from "./collapse.js";
import { coverageOf, placeGoals, stripFor } from "./goalplacing.js";
import { remountDeps } from "./storymap.js";
const INPUT = %s;
const emit = (value) => console.log(JSON.stringify(value));
"""

# The shim has to be in place before dom.js is imported, and an ES module's
# imports are hoisted -- so it goes first, as a module of its own.
_DOM_PREAMBLE = (
    'import { click, find, hasClass, press, text } from "./fakedom.js";\n'
    'import { diagram } from "./storygraph.js";\n'
) + _PREAMBLE


@pytest.fixture(scope="module")
def run_js(tmp_path_factory):
    node = _node_binary()
    if node is None:
        pytest.skip("no node available -- `pip install -e \".[dev]\"` provides one")
    workspace = tmp_path_factory.mktemp("storymap-js")
    (workspace / "package.json").write_text('{"type": "module"}')
    (workspace / "fakedom.js").write_text(_FAKE_DOM)
    for name in _MODULES:
        shutil.copy(_JS_DIR / name, workspace / name)

    def run(body: str, payload=None, dom: bool = False):
        script = workspace / "driver.js"
        preamble = _DOM_PREAMBLE if dom else _PREAMBLE
        script.write_text(preamble % json.dumps(payload if payload is not None else {}) + body)
        done = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60, check=False,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


# -- the fixture book --------------------------------------------------------
#
# Four threads over a terminus every one of them reaches:
#
#   alpha  a1 a2 a3 a4 -> j1 ------------> T     (a long solitary run, then a join)
#   beta          j1 -> b1 b2 b3 -> j2 --> T     (meets alpha at j1, gamma at j2)
#   gamma                     j2 -> c1 --> T
#   delta  d1 d2 ------------------------> T     (meets nobody but the ending)
#
# Listed alpha, gamma, beta, delta -- a plausible name order, and a tangled one:
# beta is what alpha and gamma both meet, yet it sits on the far side of gamma.

_PATHS = {
    "alpha": ["a1", "a2", "a3", "a4", "j1", "T"],
    "gamma": ["j2", "c1", "T"],
    "beta": ["j1", "b1", "b2", "b3", "j2", "T"],
    "delta": ["d1", "d2", "T"],
}
_TICKS = {
    "a1": 0, "a2": 10, "a3": 20, "a4": 30, "j1": 40,
    "b1": 50, "b2": 60, "b3": 70, "j2": 80, "c1": 90,
    "d1": 5, "d2": 15, "T": 200,
}


def _graph():
    nodes = [
        {
            "id": eid,
            "title": eid.upper(),
            "start_tick": tick,
            "end_tick": tick + 1,
            "start_label": f"Day {tick}",
            "end_label": f"Day {tick + 1}",
            # Coarse-to-fine: everything above the finest pair becomes a period
            # band, so three components give one "Year 1" header over the rows.
            "start_parts": ["Year 1", "Spring", f"Day {tick}"],
            "end_parts": ["Year 1", "Spring", f"Day {tick + 1}"],
            "scheduled": True,
            "is_convergence": False,
            "is_divergence": False,
            "is_terminus": eid == "T",
        }
        for eid, tick in _TICKS.items()
    ]
    edges = []
    for pid, path in _PATHS.items():
        for before, after in pairwise(path):
            edges.append({"from": before, "to": after, "plotlines": [pid]})
    plotlines = [
        {"id": pid, "title": pid.title(), "events": path, "continues_into": None,
         "continues_into_at": None, "effective_events": path}
        for pid, path in _PATHS.items()
    ]
    return {"nodes": nodes, "edges": edges, "plotlines": plotlines, "terminus": "T"}


@pytest.fixture()
def graph():
    return _graph()


# -- which threads are in ----------------------------------------------------


def test_restricting_keeps_exactly_the_chosen_threads(run_js, graph):
    got = run_js("""
      const slice = restrictTo(INPUT, ["alpha", "beta"]);
      emit({
        lanes: slice.plotlines.map((p) => p.id),
        nodes: slice.nodes.map((n) => n.id).sort(),
        terminus: slice.terminus,
      });
    """, graph)

    assert got["lanes"] == ["alpha", "beta"]
    assert got["nodes"] == sorted(["a1", "a2", "a3", "a4", "j1", "b1", "b2", "b3", "j2", "T"])
    assert "c1" not in got["nodes"] and "d1" not in got["nodes"]
    assert got["terminus"] == "T"


def test_restricting_drops_edges_that_would_dangle(run_js, graph):
    """gamma's `j2 -> c1` must not survive into a slice that has no c1 in it."""
    got = run_js("""
      const slice = restrictTo(INPUT, ["alpha", "beta"]);
      const ids = new Set(slice.nodes.map((n) => n.id));
      emit({
        dangling: slice.edges.filter((e) => !ids.has(e.from) || !ids.has(e.to)),
        tags: [...new Set(slice.edges.flatMap((e) => e.plotlines))].sort(),
      });
    """, graph)

    assert got["dangling"] == []
    assert got["tags"] == ["alpha", "beta"]


def test_the_connected_preset_is_the_same_narrowing(run_js, graph):
    """`connectedTo` is now `restrictTo` over the threads that meet the focus --
    it must still exclude the ones that only share the terminus."""
    got = run_js("""
      const sub = connectedTo(INPUT, "alpha");
      emit({ lanes: sub.plotlines.map((p) => p.id).sort(), focus: sub.focus });
    """, graph)

    # beta meets alpha at j1; gamma and delta meet it only at the terminus.
    assert got["lanes"] == ["alpha", "beta"]
    assert got["focus"] == "alpha"


# -- how much of them is drawn -----------------------------------------------


def test_a_solitary_run_folds_into_one_band(run_js, graph):
    got = run_js("""
      const dense = collapseRuns(restrictTo(INPUT, ["alpha", "beta", "gamma", "delta"]));
      emit({
        nodes: dense.nodes.map((n) => n.id).sort(),
        bands: dense.bands.map((b) => ({ id: b.id, lane: b.lane, events: b.events })),
        alpha: dense.plotlines.find((p) => p.id === "alpha").effective_events,
      });
    """, graph)

    ids = [b["id"] for b in got["bands"]]
    assert ids == ["~run:alpha:a1", "~run:beta:b1"]
    assert got["bands"][0]["events"] == ["a1", "a2", "a3", "a4"]
    # The four folded scenes are gone from the drawing, one band stands for them.
    for gone in ("a1", "a2", "a3", "a4", "b1", "b2", "b3"):
        assert gone not in got["nodes"]
    assert got["alpha"] == ["~run:alpha:a1", "j1", "T"]


def test_folding_never_swallows_a_junction(run_js, graph):
    """The whole point: where threads meet always draws, whatever else folds."""
    got = run_js("""
      const dense = collapseRuns(restrictTo(INPUT, ["alpha", "beta", "gamma", "delta"]));
      emit(dense.nodes.map((n) => n.id));
    """, graph)

    for junction in ("j1", "j2", "T"):
        assert junction in got


def test_a_run_shorter_than_the_minimum_is_left_alone(run_js, graph):
    """delta's two scenes and gamma's one are not worth a click."""
    got = run_js("""
      const dense = collapseRuns(restrictTo(INPUT, ["gamma", "delta"]));
      emit({ nodes: dense.nodes.map((n) => n.id).sort(), bands: dense.bands.length });
    """, graph)

    assert got["bands"] == 0
    assert got["nodes"] == sorted(["j2", "c1", "d1", "d2", "T"])


def test_an_unfolded_band_shows_its_scenes_again(run_js, graph):
    got = run_js("""
      const slice = restrictTo(INPUT, ["alpha", "beta"]);
      const dense = collapseRuns(slice, { expanded: new Set(["~run:alpha:a1"]) });
      emit({
        nodes: dense.nodes.map((n) => n.id).sort(),
        // still *found* as a run, so "fold all" can put it back
        bands: dense.bands.map((b) => b.id),
      });
    """, graph)

    for back in ("a1", "a2", "a3", "a4"):
        assert back in got["nodes"]
    assert "~run:alpha:a1" not in got["nodes"]
    assert "~run:beta:b1" in got["nodes"]  # the other one is still folded
    assert got["bands"] == ["~run:alpha:a1", "~run:beta:b1"]


def test_folding_rewires_the_edges_around_a_band(run_js, graph):
    got = run_js("""
      const dense = collapseRuns(restrictTo(INPUT, ["alpha", "beta"]));
      emit(dense.edges.map((e) => `${e.from}->${e.to}`).sort());
    """, graph)

    assert "~run:alpha:a1->j1" in got   # the run leads into the join
    assert "j1->~run:beta:b1" in got    # and out the other side
    assert not [e for e in got if e.startswith("a2") or e.endswith("a3")]


# -- where everything goes ---------------------------------------------------


def _cost(order, paths, terminus="T"):
    """The arrangement cost layout.js minimises: for every pair of threads that
    share a non-terminus event, how far apart their columns sit."""
    where = {pid: i for i, pid in enumerate(order)}
    events = {pid: {e for e in path if e != terminus} for pid, path in paths.items()}
    total = 0
    for one in order:
        for other in order:
            if one >= other:
                continue
            shared = len(events[one] & events[other])
            if shared:
                total += shared * abs(where[one] - where[other])
    return total


def test_lane_order_puts_threads_that_meet_side_by_side(run_js, graph):
    got = run_js("""
      emit(orderLanes(INPUT.plotlines, { terminus: INPUT.terminus }).map((p) => p.id));
    """, graph)

    book = list(_PATHS)
    assert _cost(got, _PATHS) < _cost(book, _PATHS), (
        f"{got} is no tidier than the book's own order {book}"
    )
    # beta is what alpha and gamma both meet, so it belongs between them.
    assert abs(got.index("alpha") - got.index("beta")) == 1
    assert abs(got.index("gamma") - got.index("beta")) == 1


def test_lane_order_is_deterministic_and_never_worse_than_the_book(run_js, graph):
    got = run_js("""
      const once = orderLanes(INPUT.plotlines, { terminus: INPUT.terminus }).map((p) => p.id);
      const twice = orderLanes(INPUT.plotlines, { terminus: INPUT.terminus }).map((p) => p.id);
      // the same threads in the reverse book order should also be tidied, not
      // merely reversed back
      const flipped = orderLanes([...INPUT.plotlines].reverse(),
                                 { terminus: INPUT.terminus }).map((p) => p.id);
      emit({ once, twice, flipped });
    """, graph)

    assert got["once"] == got["twice"]
    assert _cost(got["flipped"], _PATHS) <= _cost(list(reversed(list(_PATHS))), _PATHS)


def test_a_thread_keeps_its_colour_when_the_selection_changes(run_js, graph):
    """Identity is keyed to the book, position to the view -- the promise the
    picker makes every time a writer ticks another thread on."""
    got = run_js("""
      const book = INPUT.plotlines.map((p) => p.id);
      const colorOf = (id) => `c${book.indexOf(id)}`;
      const of = (ids) => {
        const lanes = layoutGraph(restrictTo(INPUT, ids), { colorOf }).lanes;
        return Object.fromEntries(lanes.map((l) => [l.id, l.color]));
      };
      emit({ pair: of(["alpha", "beta"]), all: of(book) });
    """, graph)

    assert got["pair"]["alpha"] == got["all"]["alpha"]
    assert got["pair"]["beta"] == got["all"]["beta"]


def test_an_expanded_row_pushes_the_rows_below_it_down(run_js, graph):
    """The whole reason row height is injected: a scene opened in place has to
    move everything under it, and the edges have to follow."""
    got = run_js("""
      const slice = restrictTo(INPUT, ["alpha"]);
      const flat = layoutGraph(slice, {});
      const grown = layoutGraph(slice, {
        heightOf: (n) => (n.id === "a2" ? geometry.ROW_H + 200 : geometry.ROW_H),
      });
      const yOf = (l) => Object.fromEntries(l.nodes.map((n) => [n.id, n.y]));
      const edge = (l) => l.edges.find((e) => e.from === "a4" && e.to === "j1");
      emit({
        flat: yOf(flat), grown: yOf(grown),
        flatEdge: edge(flat), grownEdge: edge(grown),
        flatHeight: flat.height, grownHeight: grown.height,
      });
    """, graph)

    # Everything above the expanded row is untouched...
    assert got["grown"]["a1"] == got["flat"]["a1"]
    # ...the row itself grows downward from where it was...
    assert got["grown"]["a2"] == got["flat"]["a2"] + 100  # centre of a 200px-taller row
    # ...and every row below moves by the full amount, once.
    for below in ("a3", "a4", "j1", "T"):
        assert got["grown"][below] == got["flat"][below] + 200
    # The edges are re-anchored to the moved nodes, not left behind.
    assert got["grownEdge"]["y1"] == got["flatEdge"]["y1"] + 200
    assert got["grownEdge"]["y2"] == got["flatEdge"]["y2"] + 200
    assert got["grownHeight"] == got["flatHeight"] + 200


def test_period_grouping_honours_row_height_too(run_js, graph):
    """The calendar rail re-computes every y, so it has to be told about heights
    as well -- otherwise expanding a scene moves the dots and not the bands."""
    got = run_js("""
      const slice = restrictTo(INPUT, ["alpha"]);
      const tall = (n) => (n.id === "a2" ? geometry.ROW_H + 120 : geometry.ROW_H);
      const flat = applyPeriodGrouping(layoutGraph(slice, {}), {});
      const grown = applyPeriodGrouping(layoutGraph(slice, { heightOf: tall }),
                                        { heightOf: tall });
      const yOf = (m) => Object.fromEntries(m.nodes.map((n) => [n.id, n.y]));
      emit({
        flat: yOf(flat), grown: yOf(grown),
        headers: flat.headers.map((h) => h.label),
        rowsCarryTheirPeriod: flat.nodes.every((n) => typeof n.when === "string"),
      });
    """, graph)

    assert got["rowsCarryTheirPeriod"]
    assert got["headers"] == ["Year 1"]  # one band, the whole thread inside it
    assert got["grown"]["a1"] == got["flat"]["a1"]
    for below in ("a3", "a4", "j1", "T"):
        assert got["grown"][below] == got["flat"][below] + 120


def test_the_gutter_never_squeezes_the_titles_past_the_floor(run_js, graph):
    """Rows are absolutely positioned but wrap, so a narrow title column makes
    them overlap. The layout asks for width instead, and the pane scrolls."""
    got = run_js("""
      const all = layoutGraph(restrictTo(INPUT, INPUT.plotlines.map((p) => p.id)), {});
      emit({ width: all.width, minWidth: all.minWidth, floor: geometry.TEXT_MIN });
    """, graph)

    assert got["minWidth"] >= got["width"] + got["floor"]


def test_a_band_rides_as_an_ordinary_row(run_js, graph):
    """Folding must not disturb the layout: the band sits where its scenes did."""
    got = run_js("""
      const dense = collapseRuns(restrictTo(INPUT, INPUT.plotlines.map((p) => p.id)));
      const model = applyPeriodGrouping(layoutGraph(dense, {}), {});
      const rows = model.nodes.slice().sort((a, b) => a.y - b.y).map((n) => n.id);
      const band = model.nodes.find((n) => n.id === "~run:alpha:a1");
      emit({ rows, band: { title: band.title, when: band.when, isBand: band.isBand } });
    """, graph)

    rows = got["rows"]
    # It sorts by the timing of the scenes it swallowed, so it lands where they
    # were: after nothing on its own thread, before the join they lead into, and
    # interleaved with the other threads exactly as those scenes would have been.
    assert rows.index("~run:alpha:a1") < rows.index("j1") < rows.index("~run:beta:b1")
    assert rows.index("~run:alpha:a1") < rows.index("d1")  # tick 0 before tick 5
    assert rows[-1] == "T"
    assert got["band"]["isBand"]
    assert got["band"]["title"] == "4 scenes on Alpha"
    assert got["band"]["when"]  # dated like any other row, from its first scene


def test_a_junction_that_only_a_hidden_thread_made_one_stops_being_one(run_js, graph):
    """j2 is where beta meets gamma. Deselect gamma and it is just another scene
    beta walks through -- so it folds into beta's run rather than standing alone,
    the same honesty the role badges already have about a narrowed view."""
    got = run_js("""
      const withGamma = collapseRuns(restrictTo(INPUT, ["alpha", "beta", "gamma"]));
      const without = collapseRuns(restrictTo(INPUT, ["alpha", "beta"]));
      const run = (g) => g.bands.find((b) => b.lane === "beta").events;
      emit({ withGamma: run(withGamma), without: run(without) });
    """, graph)

    assert got["withGamma"] == ["b1", "b2", "b3"]
    assert got["without"] == ["b1", "b2", "b3", "j2"]


# -- what it looks like ------------------------------------------------------
#
# The renderer is the one part of the map a pure-data test cannot reach, and the
# part a browser would fail loudest on. These build it against a deliberately
# thin fake DOM: not a rendering check (nothing here knows what a pixel is) but a
# check that the drawing is *assembled* -- every node gets a row, a band reads as
# a band, and a click reaches the callback that owns the state.


def _drawn(run_js, graph, selection, body):
    return run_js("""
      const slice = restrictTo(INPUT, SELECTION);
      const dense = collapseRuns(slice);
      const model = applyPeriodGrouping(layoutGraph(dense, {}), {});
      const stub = () => { const c = document.createElement("article"); c.className = "peek-card"; return c; };
      const calls = [];
      const pane = diagram(model, {
        expanded: new Set(), cardFor: stub, focusEvent: null,
        onToggleEvent: (n) => calls.push(["event", n.id]),
        onToggleBand: (n) => calls.push(["band", n.id]),
      });
    """.replace("SELECTION", json.dumps(selection)) + body, graph, dom=True)


def test_every_drawn_node_gets_exactly_one_row(run_js, graph):
    got = _drawn(run_js, graph, ["alpha", "beta"], """
      emit({
        nodes: model.nodes.length,
        rows: find(pane, "sg-row").length,
        bandRows: find(pane, "sg-row").filter(hasClass("is-band")).length,
        bandDots: find(pane, "sg-dot").filter(hasClass("is-band")).length,
        heads: find(pane, "sg-row-head").length,
        periodBands: find(pane, "sg-head").length,
      });
    """)

    assert got["rows"] == got["nodes"]
    assert got["heads"] == got["nodes"]  # every row is clickable
    # alpha's run and beta's: one row each, and one hollow dot each
    assert got["bandRows"] == 2
    assert got["bandDots"] == 2
    assert got["periodBands"] >= 1


def test_a_band_row_says_how_much_story_it_is_holding(run_js, graph):
    got = _drawn(run_js, graph, ["alpha", "beta"], """
      const band = find(pane, "sg-row").filter(hasClass("is-band"))[0];
      emit({ label: text(band), twisty: find(band, "twisty").map(text) });
    """)

    assert "4 scenes on Alpha" in got["label"]
    assert got["twisty"] == ["+"]  # the same twisty Akasha's tree browser uses


def test_clicking_a_row_reaches_the_state_that_owns_it(run_js, graph):
    """The renderer holds no state: a click has to come back out to storymap.js,
    which is what decides to expand and re-lay-out."""
    got = _drawn(run_js, graph, ["alpha", "beta"], """
      const rows = find(pane, "sg-row");
      const scene = rows.find((r) => !String(r.className).includes("is-band"));
      const band = rows.find((r) => String(r.className).includes("is-band"));
      click(find(scene, "sg-row-head")[0]);
      click(find(band, "sg-row-head")[0]);
      emit(calls);
    """)

    kinds = [kind for kind, _ in got]
    assert kinds == ["event", "band"]
    assert got[1][1].startswith("~run:")


def test_an_expanded_row_carries_its_card(run_js, graph):
    got = _drawn(run_js, graph, ["alpha", "beta"], """
      emit({ cards: find(pane, "peek-card").length, expanded: find(pane, "expanded").length });
    """)

    # nothing is open by default: every scene starts as one legible line
    assert got == {"cards": 0, "expanded": 0}


def test_expanding_a_scene_puts_the_card_in_that_row(run_js, graph):
    got = run_js("""
      const slice = restrictTo(INPUT, ["alpha"]);
      const model = applyPeriodGrouping(layoutGraph(slice, {}), {});
      const stub = () => { const c = document.createElement("article"); c.className = "peek-card"; return c; };
      const pane = diagram(model, {
        expanded: new Set(["a2"]), cardFor: stub, focusEvent: null,
        onToggleEvent: () => {}, onToggleBand: () => {},
      });
      const open = find(pane, "expanded");
      emit({
        opened: open.length,
        forEvent: open[0].dataset.event,
        cardsInside: find(open[0], "peek-card").length,
        cardsElsewhere: find(pane, "peek-card").length,
      });
    """, graph, dom=True)

    assert got["opened"] == 1
    assert got["forEvent"] == "a2"
    assert got["cardsInside"] == 1
    assert got["cardsElsewhere"] == 1  # only the open row has one


def test_threads_past_the_palette_stay_distinct(run_js):
    """Twelve hues, three strokes. The old version of this test defined its own
    `paletteish()` and asserted against that -- a mirror of the code, which
    cannot fail when the code is wrong. This drives the real palette through the
    real layout and the real renderer.
    """
    n = 26  # two full turns of the twelve hues, plus two
    nodes = [{
        "id": f"s{i}", "title": f"s{i}", "start_tick": i * 10, "end_tick": i * 10 + 1,
        "scheduled": True, "start_label": f"t{i}", "end_label": None,
        "start_parts": ["Y1", "M1", f"D{i}"], "end_parts": None,
        "is_convergence": False, "is_divergence": False, "is_terminus": False,
    } for i in range(n)]
    nodes.append({
        "id": "end", "title": "end", "start_tick": 9999, "end_tick": 10000,
        "scheduled": True, "start_label": "t9999", "end_label": None,
        "start_parts": ["Y1", "M1", "D99"], "end_parts": None,
        "is_convergence": False, "is_divergence": False, "is_terminus": True,
    })
    payload = {
        "nodes": nodes,
        "edges": [{"from": f"s{i}", "to": "end", "plotlines": [f"p{i}"]} for i in range(n)],
        "plotlines": [{"id": f"p{i}", "title": f"P{i}", "events": [f"s{i}", "end"],
                       "continues_into": None, "continues_into_at": None,
                       "effective_events": [f"s{i}", "end"]} for i in range(n)],
        "terminus": "end",
    }

    got = run_js("""
      const ids = INPUT.plotlines.map((p) => p.id);
      const layout = layoutGraph(restrictTo(INPUT, ids), {});
      const model = applyPeriodGrouping(layout, {});
      const pane = diagram(model, { expanded: new Set(), cardFor: () => null,
        onToggleEvent: () => {}, onToggleBand: () => {}, onToggleGroup: () => {},
        focusEvent: null });
      emit({
        threads: layout.lanes.length,
        pairs: [...new Set(layout.lanes.map((l) => `${l.color}|${l.dash}`))].length,
        hues: [...new Set(layout.lanes.map((l) => l.color))].length,
        strokes: [...new Set(layout.lanes.map((l) => l.dash))].sort(),
        // the stroke has to reach the SVG, not merely the model
        drawn: [...new Set(find(pane, "sg-edge").map(
          (p) => p.attrs["stroke-dasharray"] || ""))].sort(),
        // ...and both marks that stand for a thread have to show it
        dotMarks: [...new Set(find(pane, "sg-lane-dot").map(
          (d) => `${hasClass("is-dashed")(d)}${hasClass("is-dotted")(d)}`))].sort(),
      });
    """, payload, dom=True)

    assert got["threads"] == 26
    assert got["hues"] == 12                       # the palette really does run out
    assert got["strokes"] == ["", "2 4", "7 4"]    # and the stroke picks up the slack
    assert got["pairs"] == 26, "two threads share a colour *and* a stroke"
    assert got["drawn"] == ["", "2 4", "7 4"]      # reaching the actual paths
    assert len(got["dotMarks"]) == 3               # solid, dashed and dotted discs


# -- how edges are routed ----------------------------------------------------
#
# These pin the shape itself, because the bug they came from was invisible to
# every other kind of check: the drawing was *correct* (right endpoints, right
# colour, right thread) and still unreadable, because two threads occupied the
# same pixels. Endpoints alone cannot say that; the path between them can.


def _edge(run_js, graph, x1, y1, x2, y2):
    return run_js("""
      const model = { headers: [], nodes: [], rows: [], lanes: [], width: 100, minWidth: 500,
        height: 400, edges: [{ from: "a", to: "b", x1: X1, y1: Y1, x2: X2, y2: Y2,
                               color: "c", dash: "", isFocus: false }] };
      const pane = diagram(model, { expanded: new Set(), cardFor: () => null,
        onToggleEvent: () => {}, onToggleBand: () => {}, focusEvent: null });
      emit(find(pane, "sg-edge")[0].attrs.d);
    """.replace("X1", str(x1)).replace("Y1", str(y1))
       .replace("X2", str(x2)).replace("Y2", str(y2)), graph, dom=True)


def test_a_thread_staying_in_its_lane_is_drawn_straight(run_js, graph):
    assert _edge(run_js, graph, 22, 100, 22, 158) == "M 22 100 L 22 158"


def test_a_joining_thread_holds_its_own_column_until_the_turn(run_js, graph):
    """The regression that started this: with a symmetric S-curve, this exact
    edge reached x=22 at y=231 and then ran along the top of the line already
    descending that column, so two threads read as one."""
    got = _edge(run_js, graph, 56, 173, 22, 289)

    assert got.startswith("M 56 173 V "), got
    # It descends in *its* column (56) and only reaches the target's (22) in the
    # final turn -- so the target column is never mentioned before the curve.
    straight, _, curve = got.partition("Q")
    assert "22" not in straight, f"enters the target column early: {got}"
    assert curve.strip().startswith("56 289"), curve  # the corner, then across

    # The turn begins below the halfway point the old shape used, and above the
    # node itself -- i.e. late, but not a right angle at the node.
    turn_y = float(straight.split("V")[1].strip())
    assert (173 + 289) / 2 < turn_y < 289, turn_y


def test_a_departing_thread_turns_out_at_once(run_js, graph):
    """Mirror image: leaving a thread, take the new column immediately, so the
    departure is visible at the node it departs from rather than three rows on."""
    got = _edge(run_js, graph, 22, 100, 56, 300)

    assert got.startswith("M 22 100 Q 56 100,"), got
    assert got.endswith("V 300"), got
    # "M 22 100 Q 56 100, 56 135 V 300" -> the y it finishes turning at
    turn_y = float(got.split("Q")[1].split(",")[1].split("V")[0].split()[1])
    assert 100 < turn_y < (100 + 300) / 2, turn_y


def test_a_thread_reaching_further_turns_earlier(run_js, graph):
    """Several threads joining one node should nest, not cross: the one coming
    from further away starts its sweep higher up."""
    def turn_starts_at(d):
        return float(d.split("V")[1].split("Q")[0].strip())

    near = turn_starts_at(_edge(run_js, graph, 56, 100, 22, 300))
    far = turn_starts_at(_edge(run_js, graph, 158, 100, 22, 300))

    assert far < near, (far, near)


def test_two_threads_joining_one_node_never_share_a_column(run_js, graph):
    """The property the fix exists for, stated directly."""
    joining = _edge(run_js, graph, 56, 173, 22, 289)
    already_there = _edge(run_js, graph, 22, 231, 22, 289)

    # the straight one owns column 22 from y=231 down
    assert already_there == "M 22 231 L 22 289"
    # and the joining one is still in column 56 at that height
    turn_y = float(joining.split("V")[1].split("Q")[0].strip())
    assert turn_y > 231, f"the joining thread enters column 22 at y={turn_y}"


# -- rows in time order ------------------------------------------------------
#
# A book where one thread carries an undated scene early on and another runs a
# year past the ending. Folded, this looks fine -- a band takes its first scene's
# date. Unfolded, it was the shape that made the calendar rail announce Year 2
# in the middle of Year 1: the undated scene sorted as infinitely late and took
# everything downstream of it along.

_DRIFT = {
    "nodes": [
        # (id, tick) -- `undated` has no timing at all
        {"id": "opens", "tick": 0}, {"id": "undated", "tick": None},
        {"id": "early", "tick": 48}, {"id": "ending", "tick": 200},
        {"id": "next-year", "tick": 8664},
    ],
    "paths": {
        "drifting": ["opens", "undated", "early", "ending"],
        "long": ["opens", "next-year"],
    },
}


def _drift_graph():
    def parts(tick):
        year, rest = divmod(tick, 8640)
        month, day = divmod(rest, 720)
        return [f"Year {year + 1}", f"Month {month + 1}", f"Day {day // 24 + 1}"]

    nodes = []
    for spec in _DRIFT["nodes"]:
        tick = spec["tick"]
        nodes.append({
            "id": spec["id"], "title": spec["id"],
            "start_tick": tick, "end_tick": None if tick is None else tick + 1,
            "start_label": None if tick is None else f"tick {tick}",
            "end_label": None, "scheduled": tick is not None,
            "start_parts": None if tick is None else parts(tick),
            "end_parts": None,
            "is_convergence": False, "is_divergence": False, "is_terminus": False,
        })
    edges = [
        {"from": a, "to": b, "plotlines": [pid]}
        for pid, path in _DRIFT["paths"].items() for a, b in pairwise(path)
    ]
    plotlines = [
        {"id": pid, "title": pid.title(), "events": path, "continues_into": None,
         "continues_into_at": None, "effective_events": path}
        for pid, path in _DRIFT["paths"].items()
    ]
    return {"nodes": nodes, "edges": edges, "plotlines": plotlines, "terminus": None}


@pytest.fixture()
def drift():
    return _drift_graph()


def test_an_undated_scene_does_not_drag_its_thread_to_the_bottom(run_js, drift):
    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const layout = layoutGraph(restrictTo(INPUT, all), {});
      emit(layout.nodes.slice().sort((a, b) => a.row - b.row).map((n) => n.id));
    """, drift)

    # `early` happens on tick 48 and must be drawn there, not below a scene a
    # year later just because an undated scene sits in front of it.
    assert got.index("early") < got.index("next-year")
    assert got.index("ending") < got.index("next-year")
    # and the undated scene lands between the dated ones either side of it
    assert got.index("opens") < got.index("undated") < got.index("early")


def test_the_calendar_rail_never_doubles_back(run_js, drift):
    """The reported symptom: Year 2 in the middle of Year 1. A period band is
    only meaningful if the rows under it are the rows in that period, so the
    sequence of top-level bands has to run forward."""
    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const model = applyPeriodGrouping(layoutGraph(restrictTo(INPUT, all), {}), {});
      emit({
        headers: model.headers.filter((h) => h.level === 0).map((h) => h.label),
        rows: model.nodes.slice().sort((a, b) => a.y - b.y)
          .map((n) => [n.id, n.startTick]),
      });
    """, drift)

    years = got["headers"]
    assert years == sorted(years), f"the rail doubles back: {years}"
    assert years == ["Year 1", "Year 2"]

    dated = [tick for _, tick in got["rows"] if tick is not None]
    assert dated == sorted(dated), f"rows are out of time order: {got['rows']}"


def test_folding_and_unfolding_agree_about_time_order(run_js, drift):
    """Folded was always fine -- a band takes its first scene's date -- so the
    bug only appeared on 'Unfold all'. The two must tell the same story."""
    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const slice = restrictTo(INPUT, all);
      const years = (g) => applyPeriodGrouping(layoutGraph(g, {}), {})
        .headers.filter((h) => h.level === 0).map((h) => h.label);
      const folded = collapseRuns(slice, { minRun: 2 });
      const opened = collapseRuns(slice, {
        minRun: 2, expanded: new Set(folded.bands.map((b) => b.id)),
      });
      emit({ folded: years(folded), opened: years(opened) });
    """, drift)

    assert got["folded"] == sorted(got["folded"]), got["folded"]
    assert got["opened"] == sorted(got["opened"]), got["opened"]


def test_escape_closes_an_open_scene(run_js, graph):
    """Promised in the design and easy to forget: a scene opened in place has to
    be closeable from the keyboard, not only by finding its ✕ with the mouse."""
    got = run_js("""
      const slice = restrictTo(INPUT, ["alpha"]);
      const model = applyPeriodGrouping(layoutGraph(slice, {}), {});
      const closed = [];
      const build = (expanded) => diagram(model, {
        expanded: new Set(expanded), cardFor: () => null, focusEvent: null,
        onToggleEvent: (n) => closed.push(n.id), onToggleBand: () => {},
      });
      const openPane = build(["a2"]);
      press(find(openPane, "sg-row").find((r) => r.dataset.event === "a2"), "Escape");
      const shutPane = build([]);
      // Esc on a row that is not open must not toggle it *open*
      press(find(shutPane, "sg-row").find((r) => r.dataset.event === "a2"), "Escape");
      // nor should another key close one that is
      press(find(build(["a2"]), "sg-row").find((r) => r.dataset.event === "a2"), "a");
      emit(closed);
    """, graph, dom=True)

    assert got == ["a2"]


# -- simultaneous rows -------------------------------------------------------
#
# Two threads can hold different scenes at the same tick; a plotline's own scenes
# never can (the ordering rule forbids it). Stacked plainly they read as a
# sequence, and the order between them is only an alphabetical tie-break, so the
# map has to say they are concurrent rather than let the stack imply an order.

_AT_ONCE = {
    "nodes": {"open-a": 0, "open-b": 0, "duel": 100, "betrayal": 100,
              "aftermath": 200, "end": 300},
    "paths": {"knight": ["open-a", "duel", "aftermath", "end"],
              "spy": ["open-b", "betrayal", "end"]},
}


def _at_once_graph():
    nodes = [{
        "id": eid, "title": eid, "start_tick": t, "end_tick": t + 4, "scheduled": True,
        "start_label": f"t{t}", "end_label": f"t{t + 4}",
        "start_parts": ["Year 1", "Month 1", f"Day {t // 24 + 1}"],
        "end_parts": ["Year 1", "Month 1", f"Day {t // 24 + 1}"],
        "is_convergence": False, "is_divergence": False, "is_terminus": eid == "end",
    } for eid, t in _AT_ONCE["nodes"].items()]
    edges = [{"from": a, "to": b, "plotlines": [pid]}
             for pid, path in _AT_ONCE["paths"].items() for a, b in pairwise(path)]
    plotlines = [{"id": pid, "title": pid.title(), "events": path,
                  "continues_into": None, "continues_into_at": None,
                  "effective_events": path}
                 for pid, path in _AT_ONCE["paths"].items()]
    return {"nodes": nodes, "edges": edges, "plotlines": plotlines, "terminus": "end"}


@pytest.fixture()
def at_once():
    return _at_once_graph()


def _grouped(run_js, graph, body):
    return run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const model = applyPeriodGrouping(layoutGraph(restrictTo(INPUT, all), {}), {});
    """ + body, graph)


def test_scenes_at_one_moment_share_a_row_and_a_y(run_js, at_once):
    """The point of the whole thing: simultaneous scenes sit at the same height,
    so the diagram cannot imply an order the story has not got."""
    got = _grouped(run_js, at_once, """
      emit({
        rows: model.rows.map((r) => ({ id: r.id, y: r.y, isGroup: !!r.isGroup,
                                       nodes: r.nodes.map((n) => n.id) })),
        ys: Object.fromEntries(model.nodes.map((n) => [n.id, n.y])),
      });
    """)

    groups = [r for r in got["rows"] if r["isGroup"]]
    assert [sorted(g["nodes"]) for g in groups] == [["open-a", "open-b"],
                                                    ["betrayal", "duel"]]
    # the two scenes of a moment are at one y, on their own threads
    assert got["ys"]["duel"] == got["ys"]["betrayal"]
    assert got["ys"]["open-a"] == got["ys"]["open-b"]
    # and the moments themselves are still in time order
    assert got["ys"]["open-a"] < got["ys"]["duel"] < got["ys"]["aftermath"]


def test_a_group_takes_one_slot_not_one_per_scene(run_js, at_once):
    """Six scenes, four moments -- the map is shorter *and* truer."""
    got = _grouped(run_js, at_once, "emit({ rows: model.rows.length, nodes: model.nodes.length });")
    assert got == {"rows": 4, "nodes": 6}


def test_a_moment_hides_its_scenes_when_closed(run_js, at_once):
    """A moment is a node in a tree, and its twisty means what it means in
    Akasha's: open lists what is inside, closed hides it behind a count. It is
    open by default -- a scene you cannot read is not much of a map."""
    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const draw = (shut) => applyPeriodGrouping(
        layoutGraph(restrictTo(INPUT, all), {}), { collapsedMoments: new Set(shut) });
      const open = draw([]);
      const id = open.rows.find((r) => r.isGroup && r.nodes.some((n) => n.id === "duel")).id;
      const shut = draw([id]);
      const at = (m, nid) => m.rows.find((r) => r.nodes.some((n) => n.id === nid));
      emit({
        id,
        // closing changes what is *drawn*, never how many moments there are
        rowsOpen: open.rows.length, rowsShut: shut.rows.length,
        collapsed: [!!at(open, "duel").collapsed, !!at(shut, "duel").collapsed],
        // the scenes still belong to it, and still share its y
        stillTogether: at(shut, "duel").nodes.map((n) => n.id).sort(),
        sameY: at(shut, "duel").y === at(shut, "betrayal").y,
        // the other moment is untouched
        otherOpen: !at(shut, "open-a").collapsed,
      });
    """, at_once)

    assert got["id"] == "~at:100:betrayal"
    assert got["rowsOpen"] == got["rowsShut"] == 4
    assert got["collapsed"] == [False, True]
    assert got["stillTogether"] == ["betrayal", "duel"]
    assert got["sameY"] is True
    assert got["otherOpen"] is True


def test_a_closed_moment_draws_a_count_and_no_scenes(run_js, at_once):
    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const build = (shut) => {
        const m = applyPeriodGrouping(layoutGraph(restrictTo(INPUT, all), {}),
                                      { collapsedMoments: new Set(shut) });
        return diagram(m, { expanded: new Set(), cardFor: () => null,
          onToggleEvent: () => {}, onToggleBand: () => {}, onToggleGroup: () => {},
          focusEvent: null });
      };
      const open = build([]);
      const shut = build(["~at:100:betrayal"]);
      emit({
        scenesOpen: find(open, "sg-group-scene").length,
        scenesShut: find(shut, "sg-group-scene").length,
        marksOpen: find(open, "twisty-btn").map((b) => text(b)),
        marksShut: find(shut, "twisty-btn").map((b) => text(b)),
        shutLabel: find(shut, "sg-row").filter(hasClass("collapsed")).map(text)[0],
      });
    """, at_once, dom=True)

    assert got["scenesOpen"] == 4
    assert got["scenesShut"] == 2            # only the still-open moment lists its scenes
    assert got["marksOpen"] == ["\u2212", "\u2212"]   # both open: minus
    assert got["marksShut"] == ["\u2212", "+"]         # the closed one offers plus
    assert got["shutLabel"].startswith("+ 2 at once")


def test_rows_at_different_ticks_are_never_grouped(run_js, graph):
    got = _grouped(run_js, graph, "emit(model.rows.filter((r) => r.isGroup).length);")
    assert got == 0


def test_an_undated_scene_never_counts_as_simultaneous(run_js, drift):
    """Two scenes with no time are not 'at the same time' -- they have no time."""
    got = _grouped(run_js, drift, """
      emit({ groups: model.rows.filter((r) => r.isGroup).length,
             undated: model.nodes.filter((n) => !n.scheduled).map((n) => n.id) });
    """)
    assert got["undated"] == ["undated"]
    assert got["groups"] == 0


def test_a_merged_moment_reads_as_one_row_with_every_scene_on_it(run_js, at_once):
    """What the reader sees, through the renderer."""
    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const model = applyPeriodGrouping(layoutGraph(restrictTo(INPUT, all), {}), {});
      const pane = diagram(model, { expanded: new Set(), cardFor: () => null,
        onToggleEvent: () => {}, onToggleBand: () => {}, onToggleGroup: () => {},
        focusEvent: null });
      emit({
        rows: find(pane, "sg-row").length,
        groupRows: find(pane, "is-group").length,
        scenesInGroups: find(pane, "sg-group-scene").length,
        times: find(pane, "sg-row-when").map(text),
      });
    """, at_once, dom=True)

    assert got["rows"] == 4          # four moments, not six scenes
    assert got["groupRows"] == 2
    assert got["scenesInGroups"] == 4
    assert len(got["times"]) == 4    # one time per row, never repeated
    assert all("at once" not in t for t in got["times"])  # the count leads the row


def test_the_toggle_reports_the_group_it_would_merge(run_js, at_once):
    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const model = applyPeriodGrouping(layoutGraph(restrictTo(INPUT, all), {}), {});
      const toggled = [];
      const pane = diagram(model, { expanded: new Set(), cardFor: () => null,
        onToggleEvent: () => {}, onToggleBand: () => {},
        onToggleGroup: (id) => toggled.push(id), focusEvent: null });
      find(pane, "twisty-btn").forEach(click);
      emit(toggled);
    """, at_once, dom=True)

    assert got == ["~at:0:open-a", "~at:100:betrayal"]


def test_a_moment_made_of_folded_stretches_closes_like_any_other(run_js):
    """A moment can hold folded stretches rather than single scenes -- it still
    opens and closes the same way, and the twisty still lives on its bar."""
    paths = {"one": ["a1", "a2", "a3", "join"], "two": ["b1", "b2", "b3", "join"]}
    ticks = {"a1": 0, "a2": 10, "a3": 20, "b1": 0, "b2": 10, "b3": 20, "join": 100}
    payload = {
        "nodes": [{
            "id": eid, "title": eid, "start_tick": t, "end_tick": t + 1, "scheduled": True,
            "start_label": f"t{t}", "end_label": None,
            "start_parts": ["Year 1", "Month 1", f"Day {t // 24 + 1}"], "end_parts": None,
            "is_convergence": False, "is_divergence": False, "is_terminus": False,
        } for eid, t in ticks.items()],
        "edges": [{"from": a, "to": b, "plotlines": [pid]}
                  for pid, path in paths.items() for a, b in pairwise(path)],
        "plotlines": [{"id": pid, "title": pid.title(), "events": path,
                       "continues_into": None, "continues_into_at": None,
                       "effective_events": path} for pid, path in paths.items()],
        "terminus": "join",
    }

    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const dense = collapseRuns(restrictTo(INPUT, all));
      const draw = (shut) => applyPeriodGrouping(layoutGraph(dense, {}),
                                                 { collapsedMoments: new Set(shut) });
      const pane = (m) => diagram(m, { expanded: new Set(), cardFor: () => null,
        onToggleEvent: () => {}, onToggleBand: () => {}, onToggleGroup: () => {},
        focusEvent: null });
      const open = draw([]);
      const group = open.rows.find((r) => r.isGroup);
      emit({
        bandsInMoment: group.nodes.filter((n) => n.isBand).length,
        scenesWhenOpen: find(pane(open), "sg-group-scene").length,
        scenesWhenShut: find(pane(draw([group.id])), "sg-group-scene").length,
        toggles: find(pane(draw([group.id])), "twisty-btn").length,
      });
    """, payload, dom=True)

    assert got["bandsInMoment"] == 2
    assert got["scenesWhenOpen"] == 2
    assert got["scenesWhenShut"] == 0   # hidden behind the count
    assert got["toggles"] == 1          # and one way to bring them back


def test_every_row_carries_its_thread_colour_and_a_twisty(run_js, graph):
    """One vocabulary across the map, and across Akasha: `+` opens, `−` closes,
    and a scene's thread is legible from its own row rather than only when it
    happens to share a moment with others."""
    got = run_js("""
      const slice = restrictTo(INPUT, ["alpha", "beta"]);
      const model = applyPeriodGrouping(layoutGraph(collapseRuns(slice), {}), {});
      const build = (open) => diagram(model, { expanded: new Set(open),
        cardFor: () => null, onToggleEvent: () => {}, onToggleBand: () => {},
        onToggleGroup: () => {}, focusEvent: null });
      const shut = build([]);
      const open = build(["j1"]);
      const rowFor = (pane, id) => find(pane, "sg-row").find((r) => r.dataset.event === id);
      emit({
        rows: find(shut, "sg-row").length,
        dots: find(shut, "sg-lane-dot").length,
        marksWhenShut: find(shut, "twisty").map(text),
        j1Shut: find(rowFor(shut, "j1"), "twisty").map(text),
        j1Open: find(rowFor(open, "j1"), "twisty").map(text),
      });
    """, graph, dom=True)

    # a disc per row, and a twisty per row -- no row is a special case
    assert got["dots"] == got["rows"]
    assert len(got["marksWhenShut"]) == got["rows"]
    assert set(got["marksWhenShut"]) == {"+"}
    assert got["j1Shut"] == ["+"]
    assert got["j1Open"] == ["−"]   # the same row, once its card is open


def test_a_folded_stretch_inside_a_moment_unfolds_rather_than_opening_a_card(run_js):
    """A moment can hold bands as well as scenes. A band has no event behind it,
    so treating it as one asks the API for an id that never existed -- which is
    exactly what it did: `404 ~run:the-assayer:…`, "Could not load this scene"."""
    paths = {"one": ["a1", "a2", "a3", "join"], "two": ["b1", "b2", "b3", "join"]}
    ticks = {"a1": 0, "a2": 10, "a3": 20, "b1": 0, "b2": 10, "b3": 20, "join": 100}
    payload = {
        "nodes": [{
            "id": eid, "title": eid, "start_tick": t, "end_tick": t + 1, "scheduled": True,
            "start_label": f"t{t}", "end_label": None,
            "start_parts": ["Year 1", "Month 1", f"Day {t // 24 + 1}"], "end_parts": None,
            "is_convergence": False, "is_divergence": False, "is_terminus": False,
        } for eid, t in ticks.items()],
        "edges": [{"from": a, "to": b, "plotlines": [pid]}
                  for pid, path in paths.items() for a, b in pairwise(path)],
        "plotlines": [{"id": pid, "title": pid.title(), "events": path,
                       "continues_into": None, "continues_into_at": None,
                       "effective_events": path} for pid, path in paths.items()],
        "terminus": "join",
    }

    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const model = applyPeriodGrouping(layoutGraph(collapseRuns(restrictTo(INPUT, all)), {}), {});
      const asEvent = [], asBand = [];
      const pane = diagram(model, {
        // a band must never reach cardFor: there is no scene behind it
        expanded: new Set(), cardFor: (n) => { asEvent.push("card:" + n.id); return null; },
        onToggleEvent: (n) => asEvent.push(n.id),
        onToggleBand: (n) => asBand.push(n.id),
        onToggleGroup: () => {}, focusEvent: null,
      });
      find(pane, "sg-group-scene").forEach((s) => click(find(s, "sg-row-head")[0]));
      emit({ asEvent, asBand, twisties: find(pane, "sg-group-scene").map(
        (s) => find(s, "twisty").map(text)[0]) });
    """, payload, dom=True)

    assert got["asEvent"] == []                                   # nothing treated as a scene
    assert got["asBand"] == ["~run:one:a1", "~run:two:b1"]         # both unfold instead
    assert got["twisties"] == ["+", "+"]                           # and each says so


def test_a_row_does_not_repeat_what_the_diagram_already_says(run_js, graph):
    """Joins and splits are drawn, not written: lines converging on a dot say it,
    and the labels only cost a wrapped line. The terminus is marked on its own
    name instead, with the meaning stated once under the diagram."""
    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const model = applyPeriodGrouping(layoutGraph(restrictTo(INPUT, all), {}), {});
      const pane = diagram(model, { expanded: new Set(), cardFor: () => null,
        onToggleEvent: () => {}, onToggleBand: () => {}, onToggleGroup: () => {},
        focusEvent: null });
      // j1 is a divergence and j2 a convergence in this book
      const roles = model.nodes.filter((n) => n.isConvergence || n.isDivergence)
        .map((n) => n.id).sort();
      emit({
        roles,
        badges: find(pane, "badge").map(text),
        // the diagram still marks them -- heavier dots, which is the real signal
        markedDots: find(pane, "sg-dot").filter(
          (d) => hasClass("is-merge")(d) || hasClass("is-split")(d)).length,
        underlined: find(pane, "is-terminus").map(text),
      });
    """, graph, dom=True)

    assert got["roles"], "the fixture should contain joins/splits to omit"
    assert got["badges"] == []               # nothing is spelled out any more
    assert got["markedDots"] >= len(got["roles"])
    assert got["underlined"] == ["T"]        # the ending, marked on its own name


def test_a_moment_reads_like_the_rows_around_it(run_js, at_once):
    """A moment is a row, so it is built like one: what it is, then when it was.
    The count leads, in the same slot a scene's name occupies, and the time
    follows in the same muted slot -- so the column of names lines up whether a
    row holds one scene or three."""
    got = run_js("""
      const all = INPUT.plotlines.map((p) => p.id);
      const model = applyPeriodGrouping(layoutGraph(restrictTo(INPUT, all), {}), {});
      const pane = diagram(model, { expanded: new Set(), cardFor: () => null,
        onToggleEvent: () => {}, onToggleBand: () => {}, onToggleGroup: () => {},
        focusEvent: null });
      const bar = find(pane, "sg-group-bar")[0];
      const plain = find(pane, "sg-row").find((r) => r.dataset.event === "aftermath");
      const shape = (el) => [find(el, "twisty").length,
                             find(el, "sg-row-title").map(text)[0],
                             find(el, "sg-row-when").length];
      emit({ moment: shape(bar), scene: shape(find(plain, "sg-row-head")[0]) });
    """, at_once, dom=True)

    # same three parts, same order, in both kinds of row
    assert got["moment"][0] == got["scene"][0] == 1
    assert got["moment"][2] == got["scene"][2] == 1
    assert got["moment"][1] == "2 at once"
    assert got["scene"][1] == "aftermath"


def test_a_thread_that_owns_no_column_costs_no_width(run_js, graph):
    """A trunk the others continue into is never drawn in a column of its own --
    every one of its scenes also sits on an earlier thread. Reserving a column for
    it was blank gutter *and* a resize with nothing behind it: toggling that
    thread moved the whole title column while changing not one mark."""
    got = run_js("""
      const ids = INPUT.plotlines.map((p) => p.id);
      // beta's scenes are all shared with alpha or gamma once those are shown,
      // so build a case where one lane ends up holding nothing of its own
      const of = (sel) => {
        const l = layoutGraph(restrictTo(INPUT, sel), {});
        return {
          threads: l.lanes.length,
          columns: new Set(l.nodes.map((n) => n.column)).size,
          width: l.width,
          ownsNothing: l.lanes.filter((x) => x.column === null).map((x) => x.id),
          xs: Object.fromEntries(l.nodes.map((n) => [n.id, n.x])),
          colours: Object.fromEntries(l.nodes.map((n) => [n.id, n.color])),
        };
      };
      emit({ all: of(ids), pair: of(["alpha", "beta"]) });
    """, graph)

    for view in (got["all"], got["pair"]):
        # the gutter is as wide as the columns in use, never wider
        assert view["width"] == 22 + view["columns"] * 34, view
        # and no column is left empty between the ones that are used
        assert sorted(set(view["xs"].values())) == [
            22 + i * 34 for i in range(view["columns"])
        ]
    # identity survives the renumbering: a node keeps its thread's colour
    assert got["all"]["colours"]["a1"] == got["pair"]["colours"]["a1"]


def test_closing_the_gaps_does_not_move_a_node_to_another_thread(run_js, graph):
    """The trap in compacting columns: `lane` (which thread) and `column` (where
    it lands) become different numbers, and using one for the other silently
    repaints nodes in a neighbour's colour."""
    got = run_js("""
      const ids = INPUT.plotlines.map((p) => p.id);
      const l = layoutGraph(restrictTo(INPUT, ids), {});
      const byId = Object.fromEntries(l.lanes.map((x) => [x.id, x.color]));
      // every node's colour must be the colour of the thread it is drawn on
      const wrong = l.nodes.filter((n) => n.color !== l.lanes[n.lane].color);
      emit({ wrong: wrong.map((n) => n.id),
             alphaColour: byId.alpha,
             a1: l.nodes.find((n) => n.id === "a1").color });
    """, graph)

    assert got["wrong"] == []
    assert got["a1"] == got["alphaColour"]


# -- what survives a change of calendar ---------------------------------------
#
# Switching calendars rebuilds the map, because every label on it changes. The
# `deps` the view was mounted with are frozen at route entry, while the
# selection moves as the writer ticks threads -- and those ticks are written
# with `replaceState`, precisely so the router does *not* remount. Handing the
# frozen deps back to the remount therefore rebuilds from a selection the writer
# abandoned. `remountDeps` is what stops that.


def test_a_calendar_switch_keeps_the_threads_the_writer_ticked(run_js):
    """The reported bug. Arriving from "Connected plots" leaves out any thread
    that meets the focus only at the terminus -- "The Magister's Gambit" in the
    demo book. Ticking it on and then switching calendar used to drop it again,
    because the remount re-read the selection the URL had at route entry."""
    got = run_js("""
      const bookOrder = ["knights-road","magisters-gambit","spys-shadow","trunk","witness-tale"];
      const deps = { selection: ["knights-road","trunk","witness-tale"],
                     connectedFrom: "knights-road", focusEvent: null, hashFor: null };
      const selected = new Set([...deps.selection, "magisters-gambit"]);
      emit(remountDeps(deps, bookOrder, selected));
    """)
    assert "magisters-gambit" in got["selection"]
    assert got["selection"] == ["knights-road", "magisters-gambit", "trunk", "witness-tale"]


def test_the_entry_preset_does_not_outlive_the_selection_it_became(run_js):
    """`connectedFrom` is how the map was *entered*. Carrying it through a
    remount would re-derive "this thread and everything it meets" and beat the
    explicit selection that has since replaced it."""
    got = run_js("""
      const bookOrder = ["a","b","c"];
      emit(remountDeps({ selection: ["a"], connectedFrom: "a" }, bookOrder, new Set(["a","b"])));
    """)
    assert got["connectedFrom"] is None
    assert got["selection"] == ["a", "b"]


def test_every_thread_selected_is_carried_as_the_empty_list(run_js):
    """The URL's convention for "all of them" — so a remount after Show all does
    not pin the map to a list that a later-added thread would fall out of."""
    got = run_js("""
      const bookOrder = ["a","b","c"];
      emit(remountDeps({ selection: ["a"] }, bookOrder, new Set(bookOrder)));
    """)
    assert got["selection"] == []


def test_unrelated_deps_ride_through_untouched(run_js):
    got = run_js("""
      emit(remountDeps({ selection: [], focusEvent: "e1", hashFor: null, extra: 7 },
                       ["a"], new Set(["a"])));
    """)
    assert got["focusEvent"] == "e1" and got["extra"] == 7


# -- goals on the map --------------------------------------------------------
#
# A goal touches the timeline at one point, so it draws as one mark: on the
# scene that delivers it, or on the band standing in for that scene. What is
# under test is that the mark lands on the right row, that folding does not hide
# it, and that a goal landing nowhere visible is named rather than dropped.
#
# The marks are drawn for the *book's* goals, not the shown threads': a scene on
# screen that pays off a goal is worth seeing whoever is pursuing it. The strip
# is the narrower half, and the two are checked apart for that reason.

# One goal delivered at a junction, one inside alpha's solitary run, one with no
# scene at all -- the three cases the map has to tell apart.
_GOALS = [
    {"id": "crown", "title": "The Crown", "missing": False, "achieved": True,
     "achieved_at": "j1",
     "achieved_scene": {"id": "j1", "title": "J1", "when": "40"}},
    {"id": "seal", "title": "The Seal", "missing": False, "achieved": True,
     "achieved_at": "a3",
     "achieved_scene": {"id": "a3", "title": "A3", "when": "20"}},
    {"id": "peace", "title": "The Pact Holds", "missing": False, "achieved": False,
     "achieved_at": None, "achieved_scene": None},
]


def _with_goals(graph, lane_goals):
    return {
        **graph,
        "goals": _GOALS,
        "plotlines": [
            {**p, "goals": list(lane_goals.get(p["id"], []))} for p in graph["plotlines"]
        ],
    }


def _mapped(run_js, graph, selection, body):
    """Draw the map the way storymap.js does, goals and all."""
    return run_js("""
      const slice = restrictTo(INPUT, SELECTION);
      const dense = collapseRuns(slice);
      const placed = placeGoals(INPUT.goals, coverageOf(dense.nodes));
      const model = applyPeriodGrouping(layoutGraph(dense, {}), {});
      const clicked = [];   // goals opened
      const toggles = [];   // rows opened
      const pane = diagram(model, {
        expanded: new Set(), cardFor: () => null, focusEvent: null,
        onToggleEvent: (n) => toggles.push(n.id), onToggleBand: (n) => toggles.push(n.id),
        goalsAt: placed.marks, onGoal: (id) => clicked.push(id),
      });
      const strip = stripFor(placed, slice.plotlines);
      const marked = () => find(pane, "sg-row")
        .filter((r) => find(r, "sg-goal").length)
        .map((r) => ({ row: text(r), goals: find(r, "sg-goal").map(text) }));
    """.replace("SELECTION", json.dumps(selection)) + body, graph, dom=True)


def test_a_goal_is_drawn_on_the_row_that_delivers_it(run_js, graph):
    got = _mapped(run_js, _with_goals(graph, {"alpha": ["crown"]}), ["alpha", "beta"],
                  "emit(marked());")

    # `crown` lands on the junction; `seal` lands inside alpha's folded run.
    # `peace` lands nowhere, so it is on no row at all.
    assert sorted(g for row in got for g in row["goals"]) == ["✓ The Crown", "✓ The Seal"]
    crown = next(r for r in got if r["goals"] == ["✓ The Crown"])
    assert "J1" in crown["row"]


def test_a_goal_inside_a_folded_run_is_marked_on_the_band(run_js, graph):
    """alpha's a1-a4 fold into one band and `seal` lands on a3 inside it. The
    fold must not take the goal down with the rows it hid -- that band is
    precisely the one worth unfolding."""
    got = _mapped(run_js, _with_goals(graph, {"alpha": ["seal"]}), ["alpha", "beta"], """
      const band = find(pane, "sg-row").filter(hasClass("is-band"))
        .find((r) => find(r, "sg-goal").length);
      emit({ label: band ? text(band) : null,
             goals: band ? find(band, "sg-goal").map(text) : [] });
    """)

    assert "scenes on Alpha" in got["label"]
    assert got["goals"] == ["✓ The Seal"]


def test_the_drawing_is_left_to_say_only_what_it_is_for(run_js, graph):
    """A delivering scene used to gain a third ring on its node, on top of the
    focus and terminus rings already in play. Three circles read as a target
    rather than a scene, and the tick in the row says it without competing with
    the drawing."""
    got = _mapped(run_js, _with_goals(graph, {"alpha": ["crown"]}), ["alpha", "beta"], """
      emit({ rings: find(pane, "sg-goal-ring").length,
             dots: find(pane, "sg-dot").length,
             marks: find(pane, "sg-goal").length });
    """)

    assert got["rings"] == 0
    assert got["dots"] > 0 and got["marks"] == 2  # still drawn, still marked


def test_a_goal_with_nowhere_to_land_is_named_rather_than_dropped(run_js, graph):
    got = _mapped(run_js, _with_goals(graph, {"alpha": ["crown", "peace"]}), ["alpha"],
                  "emit(strip.map((g) => ({ id: g.id, note: g.note })));")

    assert got == [{"id": "peace", "note": "no scene yet"}]


def test_a_goal_delivered_off_the_shown_threads_says_where_it_went(run_js, graph):
    """gamma pursues the crown, which lands on j1 -- a scene gamma never walks
    through. Marking nothing would read as "this goal is going nowhere"."""
    got = _mapped(run_js, _with_goals(graph, {"gamma": ["crown"]}), ["gamma"],
                  "emit(strip.map((g) => g.note));")

    assert got == ["delivered at J1 · 40"]


def test_the_strip_ignores_goals_the_shown_threads_do_not_pursue(run_js, graph):
    """Otherwise ticking fewer threads would make the strip longer -- it would
    fill up with goals belonging to the threads the writer just hid."""
    got = _mapped(run_js, _with_goals(graph, {"delta": []}), ["delta"], """
      emit({ strip: strip.length, unplaced: placed.unplaced.length });
    """)

    assert got["unplaced"] == 3  # every goal in the book is off this slice
    assert got["strip"] == 0     # ...and delta pursues none of them


def test_clicking_a_goal_mark_reaches_the_state_that_owns_it(run_js, graph):
    """The renderer holds no state: opening the peek panel is storymap.js's job,
    so the click has to come back out the way a row's does."""
    got = _mapped(run_js, _with_goals(graph, {"alpha": ["crown"]}), ["alpha", "beta"], """
      const chip = find(pane, "sg-goal").find((c) => text(c).includes("Crown"));
      click(chip);
      emit(clicked);
    """)

    assert got == ["crown"]


def test_a_map_told_nothing_about_goals_draws_none(run_js, graph):
    """The renderer gained an optional dependency, and the book that has no
    goals passes none -- those maps must still draw."""
    got = run_js("""
      const dense = collapseRuns(restrictTo(INPUT, ["alpha", "beta"]));
      const model = applyPeriodGrouping(layoutGraph(dense, {}), {});
      const pane = diagram(model, {
        expanded: new Set(), cardFor: () => null, focusEvent: null,
        onToggleEvent: () => {}, onToggleBand: () => {},
      });
      emit({ goals: find(pane, "sg-goal").length,
             rows: find(pane, "sg-row").length });
    """, graph, dom=True)

    assert got["goals"] == 0
    assert got["rows"] > 0


# -- marks may not cost a row its height -------------------------------------
#
# A map row is absolutely positioned at the y the layout computed, and the space
# under it is exactly what `heightOf` reserved. So a row that grows marks the
# layout was not told about is drawn on top of the row beneath it. That is not
# hypothetical: it is what shipped, and in compact density four rows in five
# overlapped, printing text over text.
#
# The marks sit under the head and wrap, which is what keeps the names and the
# scene titles legible — so they *do* cost height, and the fix is that
# storymap.js measures every row carrying them and feeds the real number back.
# Height is a browser fact this harness cannot see. What it can hold is the
# contract that measurement depends on: a row carrying marks says so, and can be
# named. Break either and the overlap comes straight back.


def test_a_row_carrying_marks_says_so(run_js, graph):
    """`.has-goals` is how storymap.js finds the rows it has to measure."""
    got = _mapped(run_js, _with_goals(graph, {"alpha": ["crown"]}), ["alpha", "beta"], """
      emit(find(pane, "sg-row").map((r) => ({
        marked: hasClass("has-goals")(r), goals: find(r, "sg-goal").length,
      })));
    """)

    assert got, "the fixture drew no rows"
    for row in got:
        assert row["marked"] == (row["goals"] > 0), row
    assert sum(r["goals"] for r in got) == 2  # the junction, and alpha's band


def test_every_row_that_can_carry_marks_can_be_named(run_js, graph):
    """The measurer files a height under `dataset.event`/`dataset.slot`, so a row
    without one is a row it silently skips — and skipping is the overlap. The
    band row is the one that had no id."""
    got = _mapped(run_js, _with_goals(graph, {"alpha": ["seal"]}), ["alpha", "beta"], """
      emit(find(pane, "sg-row").map((r) => ({
        id: (r.dataset && (r.dataset.event || r.dataset.slot)) || null,
        band: hasClass("is-band")(r), marked: hasClass("has-goals")(r),
      })));
    """)

    assert any(r["band"] and r["marked"] for r in got), "no marked band in the fixture"
    for row in got:
        assert row["id"], f"a row the measurer cannot name: {row}"


def test_the_marks_sit_beside_the_head_not_inside_it(run_js, graph):
    """Each mark is a `<button>` and so is the head. Nested, the browser drops
    one of them — and it is not predictable which."""
    got = _mapped(run_js, _with_goals(graph, {"alpha": ["crown"]}), ["alpha", "beta"], """
      emit(find(pane, "sg-row-head").reduce((n, h) => n + find(h, "sg-goal").length, 0));
    """)

    assert got == 0


def test_a_mark_opens_its_goal_without_opening_the_row(run_js, graph):
    """The mark sits inside the row, so it has to stop its click reaching it."""
    got = _mapped(run_js, _with_goals(graph, {"alpha": ["crown"]}), ["alpha", "beta"], """
      click(find(pane, "sg-goal").find((c) => text(c).includes("Crown")));
      emit({ goals: clicked, rows: toggles });
    """)

    assert got["goals"] == ["crown"]
    assert got["rows"] == [], "opening a goal also toggled the scene under it"
