"""Pure cursor and placement rules for the unified scene timeline."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_JS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src" / "visualizer" / "chronos" / "static" / "js"
)
# `timelinelayout` borrows the plotline view's period grouping rather than
# growing a second one, so the driver needs both files on disk.
_MODULES = ("timelinelayout.js", "timeaxis.js")


def _node_binary():
    found = shutil.which("node")
    if found:
        return found
    try:
        import nodejs_wheel
    except ImportError:
        return None
    executable = "node.exe" if sys.platform == "win32" else "node"
    candidate = Path(nodejs_wheel.__file__).parent / "bin" / executable
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def run_js(tmp_path_factory):
    node = _node_binary()
    if node is None:
        pytest.skip("no node available -- `pip install -e \".[dev]\"` provides one")
    workspace = tmp_path_factory.mktemp("scene-timeline-js")
    (workspace / "package.json").write_text('{"type": "module"}')
    for name in _MODULES:
        shutil.copy(_JS_DIR / name, workspace / name)

    def run(body, payload=None):
        script = workspace / "driver.js"
        script.write_text(
            'import * as timeline from "./timelinelayout.js";\n'
            f"const INPUT = {json.dumps(payload or {})};\n"
            "const emit = value => console.log(JSON.stringify(value));\n"
            + body
        )
        done = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60, check=False,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


def scene(scene_id, start, end, title=None):
    return {"id": scene_id, "title": title or scene_id, "start_tick": start, "end_tick": end}


def dated(scene_id, start, end, start_parts, end_parts=None):
    """A scene as the timeline endpoint presents it, calendar parts included."""
    end_parts = end_parts or start_parts
    return {
        **scene(scene_id, start, end), "scheduled": True,
        "start_parts": start_parts, "end_parts": end_parts,
        "start_label": ", ".join(start_parts), "end_label": ", ".join(end_parts),
    }


def test_tick_and_scroll_are_inverse_even_before_tick_zero(run_js):
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, INPUT.options);
      const scroll = timeline.scrollForTick(scale, -20);
      emit({tick: timeline.tickAtScroll(scale, scroll), start: scale.startTick});
    """, {"bounds": {"start_tick": -100, "end_tick": 100},
           "options": {"viewportHeight": 600, "eventCount": 10}})
    assert got == {"tick": -20, "start": -100}


def test_a_scene_spanning_the_cursor_has_zero_distance(run_js):
    got = run_js("emit(timeline.distanceToScene(INPUT, 15));", scene("voyage", 10, 20))
    assert got == 0


def test_story_order_ranks_every_scene_once(run_js):
    payload = [scene("late", 90, 95), scene("early", 10, 20)]
    got = run_js("""
      const order = timeline.storyOrder(INPUT);
      emit({ids: order.ordered.map(s => s.id), rank: [...order.rank]});
    """, payload)
    assert got == {"ids": ["early", "late"], "rank": [["early", 0], ["late", 1]]}


def test_far_scenes_do_not_enter_the_render_window(run_js):
    payload = {
        "events": [scene("near", 50, 55), scene("far", 950, 960)],
        "bounds": {"start_tick": 0, "end_tick": 1000},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, eventCount: INPUT.events.length, zoom: 4,
      });
      const order = timeline.storyOrder(INPUT.events);
      emit(timeline.visibleScenes(order, scale, 50).map(p => p.scene.id));
    """, payload)
    assert got == ["near"]


def test_simultaneous_scenes_share_an_anchor_and_take_parallel_lanes(run_js):
    payload = {
        "events": [
            scene("short", 10, 12, "Zulu"),
            scene("long-z", 10, 30, "Zulu"),
            scene("long-a", 10, 30, "Alpha"),
        ],
        "bounds": {"start_tick": 0, "end_tick": 40},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {viewportHeight: 600, eventCount: 3});
      const order = timeline.storyOrder(INPUT.events);
      emit(timeline.visibleScenes(order, scale, 10).map(p => ({
        id: p.scene.id, side: p.side, anchor: p.anchorY,
      })));
    """, payload)
    assert [item["id"] for item in got] == ["long-a", "long-z", "short"]
    assert got[0]["anchor"] == got[1]["anchor"] == got[2]["anchor"]
    assert [item["side"] for item in got[:2]] == [0, 1]


def test_the_render_limit_never_splits_a_simultaneous_moment(run_js):
    payload = {
        "events": [scene(f"e{i}", 10, 20) for i in range(5)],
        "bounds": {"start_tick": 0, "end_tick": 40},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {viewportHeight: 600, eventCount: 5});
      const order = timeline.storyOrder(INPUT.events);
      emit(timeline.visibleScenes(order, scale, 10, {maxScenes: 2}).length);
    """, payload)
    assert got == 5


def test_no_card_is_mounted_where_the_stage_cannot_show_it(run_js):
    """Packing pushes cards away from the cursor; it must stop at the edge.

    Packing everything downward from the top instead -- the obvious way -- put
    the later half of the window below the stage, still in the DOM and behind
    `overflow: hidden`. On a Salt Road-shaped book that was two cards in five.
    Nothing else can see this: it is not an ordering bug and not a visual one,
    since the cards were invisible either way.
    """
    payload = {
        # A dense run either side of the cursor: far more scenes want the stage
        # than can fit on it, which is exactly when packing used to overflow.
        "events": [scene(f"e{i}", i * 4, i * 4 + 2) for i in range(60)],
        "bounds": {"start_tick": 0, "end_tick": 240},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, events: INPUT.events, eventCount: INPUT.events.length,
      });
      const order = timeline.storyOrder(INPUT.events);
      let worst = 0, mounted = 0;
      for (let step = 0; step <= 40; step++) {
        const tick = timeline.tickAtScroll(scale, step / 40 * scale.runHeight);
        const cards = timeline.visibleScenes(order, scale, tick, {viewportHeight: 600});
        mounted = Math.max(mounted, cards.length);
        worst = Math.max(worst, cards.filter(c => c.top >= 600 || c.top + 78 <= 0).length);
      }
      emit({worst, mounted});
    """, payload)
    assert got["worst"] == 0
    assert got["mounted"] > 0, "the sweep never mounted a card, so it proved nothing"


def test_cards_stack_away_from_the_cursor_on_both_sides(run_js):
    """Earlier scenes sit above the rule, later ones below -- never across it."""
    payload = {
        "events": [scene(f"e{i}", i * 10, i * 10 + 2) for i in range(12)],
        "bounds": {"start_tick": 0, "end_tick": 120},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, events: INPUT.events, eventCount: 12, zoom: 4,
      });
      const order = timeline.storyOrder(INPUT.events);
      emit(timeline.visibleScenes(order, scale, 60, {viewportHeight: 600})
        .map(p => ({id: p.scene.id, before: p.scene.start_tick <= 60, top: p.top})));
    """, payload)
    above = [p["top"] for p in got if p["before"]]
    below = [p["top"] for p in got if not p["before"]]
    assert above and below, f"the sweep needs cards on both sides: {got}"
    # 300 is the rule; a card is 78 tall, so "above" means it ends before it.
    assert max(above) + 78 <= 300 + 1
    assert min(below) >= 300 - 1


def test_zoom_keeps_a_cursor_tick_addressable(run_js):
    got = run_js("""
      const one = timeline.scaleFor(INPUT, {viewportHeight: 600, eventCount: 20, zoom: 1});
      const four = timeline.scaleFor(INPUT, {viewportHeight: 600, eventCount: 20, zoom: 4});
      const tick = timeline.tickAtScroll(one, timeline.scrollForTick(one, 75));
      emit(timeline.tickAtScroll(four, timeline.scrollForTick(four, tick)));
    """, {"start_tick": 0, "end_tick": 100})
    assert got == 75


def test_a_huge_empty_gap_is_capped_and_reported_as_a_break(run_js):
    payload = {
        "events": [scene("departure", 0, 10), scene("terminus", 1000, 1010)],
        "bounds": {"start_tick": 0, "end_tick": 1010},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, events: INPUT.events, eventCount: 2,
      });
      const gap = scale.map.gaps[0];
      emit({
        raw: gap.rawDuration,
        pixels: gap.displayDuration * scale.pixelsPerUnit,
        breaks: timeline.visibleBreaks(scale, 500, {viewportHeight: 600, overscan: 1000}).length,
      });
    """, payload)
    assert got["raw"] == 990
    assert got["pixels"] == pytest.approx(140)
    assert got["breaks"] == 1


def test_compressed_time_mapping_remains_invertible_inside_the_gap(run_js):
    payload = {
        "events": [scene("departure", 0, 10), scene("terminus", 1000, 1010)],
        "bounds": {"start_tick": 0, "end_tick": 1010},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, events: INPUT.events, eventCount: 2,
      });
      emit([0, 10, 500, 1000, 1010].map(
        tick => timeline.tickAtScroll(scale, timeline.scrollForTick(scale, tick)),
      ));
    """, payload)
    assert got == [0, 10, 500, 1000, 1010]


def test_ordinary_gaps_remain_proportional(run_js):
    payload = {
        "events": [scene("a", 0, 10), scene("b", 30, 40)],
        "bounds": {"start_tick": 0, "end_tick": 40},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, events: INPUT.events, eventCount: 2,
      });
      emit(scale.map.gaps.length);
    """, payload)
    assert got == 0


def test_a_scenes_side_is_stable_as_the_visible_window_moves(run_js):
    payload = {
        "events": [scene("a", 0, 10), scene("b", 20, 30), scene("c", 40, 50)],
        "bounds": {"start_tick": 0, "end_tick": 50},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, events: INPUT.events, eventCount: 3, zoom: 4,
      });
      const order = timeline.storyOrder(INPUT.events);
      const sideAt = tick => timeline.visibleScenes(order, scale, tick)
        .find(item => item.scene.id === "b").side;
      emit([sideAt(20), sideAt(40)]);
    """, payload)
    assert got == [1, 1]


# -- the book's own periods ---------------------------------------------------


def test_period_bands_mark_where_the_calendar_turns_over(run_js):
    # Four components, so two of them are coarser than the finest (cycle, clock)
    # pair the node keeps -- which is what makes a header level.
    payload = [
        dated("a", 0, 5, ["Year 1", "Spring", "Week 1", "Day 1"]),
        dated("b", 10, 15, ["Year 1", "Spring", "Week 1", "Day 3"]),
        dated("c", 40, 45, ["Year 1", "Summer", "Week 1", "Day 1"]),
        dated("d", 90, 95, ["Year 2", "Spring", "Week 1", "Day 1"]),
    ]
    got = run_js("emit(timeline.periodBands(timeline.storyOrder(INPUT).ordered));", payload)
    assert got == [
        {"tick": 0, "level": 0, "label": "Year 1"},
        {"tick": 0, "level": 1, "label": "Spring"},
        # Only the level that changed: the year is still Year 1 here.
        {"tick": 40, "level": 1, "label": "Summer"},
        {"tick": 90, "level": 0, "label": "Year 2"},
        {"tick": 90, "level": 1, "label": "Spring"},
    ]


def test_only_components_coarser_than_the_finest_pair_become_bands(run_js):
    """A Year/Month/Day calendar bands by year; the month rides on the node.

    This is `groupByPeriod`'s rule, not the rail's -- the rail borrows it so the
    two views cannot disagree about where a period starts.
    """
    payload = [
        dated("a", 0, 5, ["Year 1", "Spring", "Day 1"]),
        dated("b", 40, 45, ["Year 1", "Summer", "Day 1"]),
        dated("c", 90, 95, ["Year 2", "Spring", "Day 1"]),
    ]
    got = run_js("emit(timeline.periodBands(timeline.storyOrder(INPUT).ordered));", payload)
    assert got == [
        {"tick": 0, "level": 0, "label": "Year 1"},
        {"tick": 90, "level": 0, "label": "Year 2"},
    ]


def test_a_bare_tick_book_gets_no_period_bands(run_js):
    """No calendar means one component, which is coarser than nothing."""
    payload = [dated("a", 0, 5, ["0"]), dated("b", 90, 95, ["90"])]
    got = run_js("emit(timeline.periodBands(timeline.storyOrder(INPUT).ordered));", payload)
    assert got == []


def test_levels_turning_over_together_are_one_boundary_on_the_rail(run_js):
    payload = {
        "events": [
            dated("a", 0, 5, ["Year 1", "Spring", "Week 1", "Day 1"]),
            dated("d", 90, 95, ["Year 2", "Spring", "Week 1", "Day 1"]),
        ],
        "bounds": {"start_tick": 0, "end_tick": 95},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, events: INPUT.events, eventCount: 2,
      });
      const bands = timeline.periodBands(timeline.storyOrder(INPUT.events).ordered);
      emit(timeline.visiblePeriods(bands, scale, 90, {viewportHeight: 600, overscan: 5000})
        .map(b => ({tick: b.tick, labels: b.labels})));
    """, payload)
    assert got == [
        {"tick": 0, "labels": ["Year 1", "Spring"]},
        {"tick": 90, "labels": ["Year 2", "Spring"]},
    ]


def test_a_band_hangs_its_label_away_from_the_cursor(run_js):
    """The cursor's rule is drawn two layers above the bands, so a label sitting
    across its own rule gets the accent line through it. Each band hangs its
    label on the far side, which is the only reason the two never collide.
    """
    payload = {
        "events": [dated(f"e{i}", i * 60, i * 60 + 5,
                         [f"Year {i + 1}", "Spring", "Week 1", "Day 1"]) for i in range(5)],
        "bounds": {"start_tick": 0, "end_tick": 245},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, events: INPUT.events, eventCount: 5,
      });
      const bands = timeline.periodBands(timeline.storyOrder(INPUT.events).ordered);
      emit(timeline.visiblePeriods(bands, scale, 120, {viewportHeight: 600, overscan: 5000})
        .map(b => ({tick: b.tick, y: Math.round(b.y), side: b.side})));
    """, payload)
    assert got, "the sweep found no bands at all"
    for band in got:
        # 300 is the rule. Above it the label hangs up, below it hangs down --
        # always away, so the rule's own pixels are never the label's.
        assert band["side"] == ("above" if band["y"] < 300 else "below"), band


def test_the_band_the_cursor_is_parked_on_is_still_drawn(run_js):
    """The rail opens with the cursor on the book's first boundary, so this is
    the *usual* case, not an edge one. Suppressing it left the opening view with
    no band at all -- which is what a reader reports as "the bands are gone".
    """
    payload = {
        "events": [
            dated("a", 0, 5, ["Year 1", "Spring", "Week 1", "Day 1"]),
            dated("d", 900, 905, ["Year 2", "Spring", "Week 1", "Day 1"]),
        ],
        "bounds": {"start_tick": 0, "end_tick": 905},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, events: INPUT.events, eventCount: 2,
      });
      const bands = timeline.periodBands(timeline.storyOrder(INPUT.events).ordered);
      const at = tick => timeline.visiblePeriods(bands, scale, tick,
        {viewportHeight: 600, overscan: 5000}).map(b => [b.tick, b.side]);
      emit({opening: at(0), parkedOnLast: at(900)});
    """, payload)
    assert [0, "below"] in got["opening"], (
        f"the band under the opening cursor vanished: {got['opening']}"
    )
    assert [900, "below"] in got["parkedOnLast"], got["parkedOnLast"]
    # And the one behind the cursor hangs the other way.
    assert [0, "above"] in got["parkedOnLast"], got["parkedOnLast"]


def test_period_bands_off_the_stage_are_not_drawn(run_js):
    payload = {
        "events": [
            dated("a", 0, 5, ["Year 1", "Spring", "Day 1"]),
            dated("d", 900, 905, ["Year 2", "Spring", "Day 1"]),
        ],
        "bounds": {"start_tick": 0, "end_tick": 905},
    }
    got = run_js("""
      const scale = timeline.scaleFor(INPUT.bounds, {
        viewportHeight: 600, events: INPUT.events, eventCount: 2, zoom: 8,
      });
      const bands = timeline.periodBands(timeline.storyOrder(INPUT.events).ordered);
      emit(timeline.visiblePeriods(bands, scale, 900, {viewportHeight: 600})
        .map(b => b.tick));
    """, payload)
    # Zoomed in on the second boundary, the first is thousands of pixels up.
    assert got == [900]
