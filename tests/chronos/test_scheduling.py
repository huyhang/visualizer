"""Drafting without timing: unscheduled scenes and their inferred windows.

A writer sketching a thread knows the order long before the clock. These cover
the pure window inference, the relaxed rules, and the end-to-end draft workflow.
"""

import pytest

from tests.chronos.conftest import ref
from visualizer.chronos.conflicts import all_conflicts, find_temporal_conflicts
from visualizer.chronos.continuation import effective_paths
from visualizer.chronos.errors import InvalidTimeframe
from visualizer.chronos.models import EntityRef, Event, Plotline
from visualizer.chronos.ordering import validate_order
from visualizer.chronos.scheduling import unscheduled_windows, window_for
from visualizer.chronos.services import BookService, EventService, PlotlineService
from visualizer.chronos.validation import validate_event_payload

BOOK = "ember-pact"
LOC = EntityRef("ember-pact", "locations", "highkeep")


def ev(id_, start=None, end=None, location="highkeep", characters=()):
    return Event(
        id=id_,
        location=EntityRef("ember-pact", "locations", location),
        start_tick=start,
        end_tick=end,
        characters=[EntityRef("ember-pact", "characters", c) for c in characters],
    )


# -- the model ----------------------------------------------------------------


def test_is_scheduled():
    assert ev("a", 0, 10).is_scheduled
    assert not ev("a").is_scheduled


def test_payload_accepts_no_timing():
    e = validate_event_payload("a", {"location": LOC.to_dict()})
    assert e.start_tick is None and e.end_tick is None and not e.is_scheduled


def test_payload_accepts_explicit_nulls():
    e = validate_event_payload(
        "a", {"location": LOC.to_dict(), "start_tick": None, "end_tick": None}
    )
    assert not e.is_scheduled


@pytest.mark.parametrize("body", [{"start_tick": 5}, {"end_tick": 5}])
def test_half_known_timing_is_rejected(body):
    with pytest.raises(InvalidTimeframe, match="both"):
        validate_event_payload("a", {"location": LOC.to_dict(), **body})


def test_start_after_end_still_rejected():
    with pytest.raises(InvalidTimeframe):
        validate_event_payload(
            "a", {"location": LOC.to_dict(), "start_tick": 10, "end_tick": 5}
        )


# -- relaxed rules ------------------------------------------------------------


def test_unscheduled_scene_never_conflicts():
    scheduled = ev("a", 0, 24, "highkeep", ["aldric"])
    sketch = ev("b", location="emberport", characters=["aldric"])
    assert find_temporal_conflicts(sketch, [scheduled]) == []
    assert all_conflicts([scheduled, sketch]) == []


def test_ordering_skips_unscheduled_but_still_checks_the_rest():
    ok = [ev("a", 0, 10), ev("gap"), ev("c", 20, 30)]
    assert validate_order(ok) is None
    broken = [ev("a", 0, 72), ev("gap"), ev("c", 20, 30)]
    v = validate_order(broken)
    assert (v.before_id, v.after_id) == ("a", "c"), "must compare across the gap"


# -- window inference ---------------------------------------------------------


def _by_id(events):
    return {e.id: e for e in events}


def test_window_between_two_scheduled_neighbours():
    events = [ev("a", 0, 24), ev("x"), ev("c", 96, 100)]
    paths = {"p": ["a", "x", "c"]}
    w = window_for("x", paths, _by_id(events))
    assert (w.earliest, w.latest) == (24, 96)
    assert not w.impossible


def test_window_open_ended_when_only_one_side_is_known():
    events = [ev("a", 0, 24), ev("x")]
    w = window_for("x", {"p": ["a", "x"]}, _by_id(events))
    assert (w.earliest, w.latest) == (24, None)


def test_window_skips_over_other_unscheduled_scenes():
    events = [ev("a", 0, 24), ev("y"), ev("x"), ev("c", 96, 100)]
    w = window_for("x", {"p": ["a", "y", "x", "c"]}, _by_id(events))
    assert (w.earliest, w.latest) == (24, 96), "must look past the undated neighbour"


def test_window_is_unconstrained_when_nothing_is_dated():
    w = window_for("x", {"p": ["y", "x", "z"]}, _by_id([ev("x"), ev("y"), ev("z")]))
    assert w.unconstrained and not w.impossible


def test_constraints_from_several_threads_compound():
    events = [ev("a", 0, 24), ev("b", 0, 40), ev("x"), ev("c", 96, 100), ev("d", 60, 70)]
    paths = {"p1": ["a", "x", "c"], "p2": ["b", "x", "d"]}
    w = window_for("x", paths, _by_id(events))
    # tightest lower bound (40) and tightest upper bound (60) both apply
    assert (w.earliest, w.latest) == (40, 60)


def test_impossible_window_is_detected_across_threads():
    """Neither thread is out of order on its own, but together they leave no room."""
    events = [ev("late", 90, 96), ev("x"), ev("early", 40, 50)]
    paths = {"p1": ["late", "x"], "p2": ["x", "early"]}
    w = window_for("x", paths, _by_id(events))
    assert (w.earliest, w.latest) == (96, 40)
    assert w.impossible
    # and no single-thread ordering check would have caught it
    for path in paths.values():
        assert validate_order([_by_id(events)[e] for e in path]) is None


def test_unscheduled_windows_covers_only_undated_scenes():
    events = [ev("a", 0, 24), ev("x"), ev("y")]
    got = unscheduled_windows(events, effective_paths([Plotline("p", ["a", "x", "y"], ["g"])]))
    assert set(got) == {"x", "y"}


# -- end to end ---------------------------------------------------------------


@pytest.fixture
def svc(story_store, fake_gate, calendar_store):
    fake_gate.add(ref("aldric"))
    for loc in ("highkeep", "emberport"):
        fake_gate.add(ref(loc, "locations"))
    books = BookService(story_store, fake_gate, calendar_store)
    books.create(BOOK, {"title": "The Ember Pact"})
    return {"books": books, "events": EventService(story_store, fake_gate),
            "plotlines": PlotlineService(story_store, fake_gate)}


def _sketch(svc, eid, start=None, end=None, location="highkeep"):
    body = {"location": ref(location, "locations").to_dict(),
            "characters": [ref("aldric").to_dict()]}
    if start is not None:
        body["start_tick"], body["end_tick"] = start, end
    return svc["events"].create(BOOK, eid, body)


def test_a_writer_can_sketch_a_whole_thread_with_no_timing(svc):
    for eid in ("opening", "middle", "finale"):
        out = _sketch(svc, eid)
        assert out["scheduled"] is False
        assert out["start_label"] is None
    svc["plotlines"].create(BOOK, "draft",
                            {"events": ["opening", "middle", "finale"], "goals": ["g"]})
    svc["books"].set_terminus(BOOK, "finale")

    report = svc["books"].validate(BOOK)
    assert report["status"] == "consistent", "a draft is not a contradiction"
    assert {u["event"] for u in report["unscheduled"]} == {"opening", "middle", "finale"}


def test_windows_appear_as_the_writer_fills_timing_in(svc):
    _sketch(svc, "opening", 0, 24)
    _sketch(svc, "middle")
    _sketch(svc, "finale", 96, 100)
    svc["plotlines"].create(BOOK, "draft",
                            {"events": ["opening", "middle", "finale"], "goals": ["g"]})

    got = svc["events"].get(BOOK, "middle")
    assert got["scheduled"] is False
    assert (got["window"]["earliest"], got["window"]["latest"]) == (24, 96)
    assert got["window"]["impossible"] is False


def test_scheduling_a_scene_clears_its_window(svc):
    _sketch(svc, "opening", 0, 24)
    _sketch(svc, "middle")
    svc["plotlines"].create(BOOK, "draft", {"events": ["opening", "middle"], "goals": ["g"]})
    current = svc["events"].get(BOOK, "middle")
    svc["events"].update(BOOK, "middle", {
        "location": ref("highkeep", "locations").to_dict(),
        "start_tick": 30, "end_tick": 40,
    }, current["rev"])
    after = svc["events"].get(BOOK, "middle")
    assert after["scheduled"] is True and after["window"] is None


def test_impossible_window_makes_the_book_conflicted(svc):
    _sketch(svc, "late", 90, 96)
    _sketch(svc, "x")
    _sketch(svc, "early", 40, 50)
    svc["plotlines"].create(BOOK, "p1", {"events": ["late", "x"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "p2", {"events": ["x", "early"], "goals": ["g"]})

    report = svc["books"].validate(BOOK)
    assert report["status"] == "conflicted"
    assert report["ordering"] == [], "no single thread is out of order"
    bad = next(u for u in report["unscheduled"] if u["event"] == "x")
    assert bad["window"]["impossible"] is True
    assert bad["window"]["code"] == "IMPOSSIBLE_WINDOW"
