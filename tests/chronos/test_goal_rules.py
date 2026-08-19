"""The goal rules, driven directly -- no app, no store, no mocks.

``goal_rules`` is where the interesting part of goals lives: the dependency
graph, and what the book has to say about whether it delivers what it set out
to. Every one of those answers is a pure function of a few dataclasses, so this
whole file runs without a server.
"""

import pytest

from visualizer.chronos.goal_rules import (
    dependency_cycle,
    dependency_cycles,
    depths,
    goal_findings,
    goals_by_event,
    served_by,
)
from visualizer.chronos.models import EntityRef, Event, Goal, Plotline
from visualizer.chronos.severity import CONFLICT, INFO

HIGHKEEP = EntityRef("ember-pact", "locations", "highkeep")


def goal(gid, depends_on=(), achieved_at=None, title=None) -> Goal:
    return Goal(id=gid, title=title, depends_on=list(depends_on), achieved_at=achieved_at)


def scene(eid, start=None, end=None, title=None) -> Event:
    return Event(id=eid, location=HIGHKEEP, start_tick=start, end_tick=end, title=title)


def thread(pid, events=(), goals=()) -> Plotline:
    return Plotline(id=pid, events=list(events), goals=list(goals))


def codes(findings, goal_id=None) -> list[str]:
    return [f.code for f in findings if goal_id is None or f.goal == goal_id]


def by_code(findings, code):
    return next(f for f in findings if f.code == code)


# -- the dependency graph ----------------------------------------------------


def test_a_goal_that_rests_on_nothing_sits_at_the_top():
    assert depths([goal("a")]) == {"a": 0}


def test_depth_is_the_longest_way_down_not_the_shortest():
    """`c` depends on `a` directly *and* through `b`. It draws below both, so
    the answer is the longer path -- otherwise an edge would point upwards."""
    graph = [goal("a"), goal("b", ["a"]), goal("c", ["a", "b"])]
    assert depths(graph) == {"a": 0, "b": 1, "c": 2}


def test_depth_ignores_a_dependency_that_is_not_there():
    assert depths([goal("a", ["ghost"])]) == {"a": 0}


def test_depth_survives_a_loop_rather_than_hanging():
    looped = [goal("a", ["b"]), goal("b", ["a"])]
    assert set(depths(looped)) == {"a", "b"}


def test_a_new_dependency_that_would_loop_is_reported_before_it_is_saved():
    stored = [goal("claim"), goal("crown", ["claim"])]
    candidate = goal("claim", ["crown"])
    assert dependency_cycle(candidate, stored) == ["claim", "crown", "claim"]


def test_a_dependency_that_would_not_loop_is_safe():
    stored = [goal("claim"), goal("crown", ["claim"])]
    assert dependency_cycle(goal("peace", ["crown"]), stored) is None


def test_only_the_goals_actually_in_the_loop_are_reported():
    """`a` can *see* the loop but is not caught in it, and saying so on `a`
    would send the writer to the one goal they cannot fix it from."""
    found = dependency_cycles([goal("a", ["b"]), goal("b", ["c"]), goal("c", ["b"])])
    assert set(found) == {"b", "c"}


def test_the_threads_pursuing_each_goal_are_read_off_the_threads():
    goals = [goal("seal"), goal("crown")]
    threads = [thread("road", goals=["seal"]), thread("shadow", goals=["seal"])]
    assert served_by(goals, threads) == {"seal": ["road", "shadow"], "crown": []}


# -- what the book says about its goals --------------------------------------


def test_a_goal_nobody_pursues_is_a_note_not_a_fault():
    found = goal_findings([goal("seal")], [], {}, {})
    assert "GOAL_UNSERVED" in codes(found)
    assert by_code(found, "GOAL_UNSERVED").severity == INFO


def test_a_goal_with_no_scene_yet_is_a_note():
    threads = [thread("road", ["a"], goals=["seal"])]
    found = goal_findings([goal("seal")], threads, {"a": scene("a")}, {"road": ["a"]})
    assert codes(found) == ["GOAL_UNACHIEVED"]
    assert by_code(found, "GOAL_UNACHIEVED").severity == INFO


def test_a_goal_delivered_on_its_own_thread_has_nothing_said_about_it():
    threads = [thread("road", ["a", "b"], goals=["seal"])]
    events = {"a": scene("a", 0, 10), "b": scene("b", 20, 30)}
    found = goal_findings(
        [goal("seal", achieved_at="b")], threads, events, {"road": ["a", "b"]}
    )
    assert found == []


def test_a_goal_achieved_on_a_scene_its_thread_never_reaches_is_a_fault():
    """The thread says it is pursuing this, and the scene that pays it off is
    not on the thread -- so the story as threaded never arrives at it."""
    threads = [thread("road", ["a"], goals=["seal"]), thread("other", ["b"])]
    events = {"a": scene("a", 0, 10), "b": scene("b", 20, 30, title="The Vigil")}
    found = goal_findings(
        [goal("seal", achieved_at="b")], threads, events,
        {"road": ["a"], "other": ["b"]},
    )
    finding = by_code(found, "GOAL_NOT_REACHED")
    assert finding.severity == CONFLICT
    assert "The Vigil" in finding.message
    assert finding.plotlines == ("road",)


def test_a_scene_reached_through_a_continuation_counts_as_reached():
    """Judged on the effective path, like every other rule: a thread that
    inherits the ending inherits the goal delivered there."""
    threads = [thread("road", ["a"], goals=["seal"])]
    events = {"a": scene("a", 0, 10), "ending": scene("ending", 40, 50)}
    found = goal_findings(
        [goal("seal", achieved_at="ending")], threads, events,
        {"road": ["a", "ending"]},  # resolved through continues_into
    )
    assert found == []


def test_an_unserved_goal_is_not_also_told_it_is_unreached():
    """One thing wrong, said once. Nobody is pursuing it -- that is the note,
    and a second finding about the same absence would be noise."""
    events = {"b": scene("b", 20, 30)}
    found = goal_findings([goal("seal", achieved_at="b")], [], events, {})
    assert codes(found) == ["GOAL_UNSERVED"]


def test_a_goal_achieved_before_the_goal_it_rests_on_is_a_fault():
    goals = [goal("claim", achieved_at="late"), goal("crown", ["claim"], achieved_at="early")]
    threads = [thread("road", ["early", "late"], goals=["claim", "crown"])]
    events = {
        "early": scene("early", 0, 10, title="The Coronation"),
        "late": scene("late", 20, 30, title="The Claim"),
    }
    found = goal_findings(goals, threads, events, {"road": ["early", "late"]})
    finding = by_code(found, "GOAL_OUT_OF_ORDER")
    assert finding.severity == CONFLICT
    assert finding.goal == "crown"
    assert "The Coronation" in finding.message and "The Claim" in finding.message


def test_a_goal_achieved_after_what_it_rests_on_is_sound():
    goals = [goal("claim", achieved_at="early"), goal("crown", ["claim"], achieved_at="late")]
    threads = [thread("road", ["early", "late"], goals=["claim", "crown"])]
    events = {"early": scene("early", 0, 10), "late": scene("late", 10, 30)}
    assert goal_findings(goals, threads, events, {"road": ["early", "late"]}) == []


def test_touching_scenes_are_in_order():
    """Half-open intervals, the same rule scene ordering uses: a dependency
    that ends exactly when the goal's scene begins is met in time."""
    goals = [goal("claim", achieved_at="first"), goal("crown", ["claim"], achieved_at="second")]
    threads = [thread("road", ["first", "second"], goals=["claim", "crown"])]
    events = {"first": scene("first", 0, 10), "second": scene("second", 10, 20)}
    assert goal_findings(goals, threads, events, {"road": ["first", "second"]}) == []


def test_two_goals_delivered_by_one_scene_are_not_out_of_order():
    """A scene can pay off a goal and its prerequisite at once -- that is a
    climax, not a contradiction."""
    goals = [goal("claim", achieved_at="s"), goal("crown", ["claim"], achieved_at="s")]
    threads = [thread("road", ["s"], goals=["claim", "crown"])]
    assert goal_findings(goals, threads, {"s": scene("s", 0, 10)}, {"road": ["s"]}) == []


def test_an_unscheduled_scene_cannot_be_too_late():
    """No timing yet is a draft state; the scene report already says so, and
    guessing an order from it would invent a fault."""
    goals = [goal("claim", achieved_at="undated"), goal("crown", ["claim"], achieved_at="dated")]
    threads = [thread("road", ["dated", "undated"], goals=["claim", "crown"])]
    events = {"dated": scene("dated", 0, 10), "undated": scene("undated")}
    found = goal_findings(goals, threads, events, {"road": ["dated", "undated"]})
    assert codes(found, "crown") == []


def test_a_goal_resting_on_one_that_has_no_scene_yet_is_a_note():
    goals = [goal("claim", title="The Claim"), goal("crown", ["claim"], achieved_at="s")]
    threads = [thread("road", ["s"], goals=["claim", "crown"])]
    found = goal_findings(goals, threads, {"s": scene("s", 0, 10)}, {"road": ["s"]})
    finding = by_code(found, "GOAL_DEPENDENCY_UNMET")
    assert finding.severity == INFO
    assert "The Claim" in finding.message


# -- data a write would refuse, which a read must still describe -------------


def test_a_dangling_dependency_is_described_rather_than_ignored():
    threads = [thread("road", ["s"], goals=["crown"])]
    found = goal_findings(
        [goal("crown", ["ghost"])], threads, {"s": scene("s")}, {"road": ["s"]}
    )
    finding = by_code(found, "GOAL_DEPENDENCY_MISSING")
    assert finding.severity == INFO
    assert "'ghost'" in finding.message


def test_a_loop_in_stored_data_is_described_on_every_goal_in_it():
    goals = [goal("a", ["b"]), goal("b", ["a"])]
    found = goal_findings(goals, [], {}, {})
    assert {f.goal for f in found if f.code == "GOAL_CYCLE"} == {"a", "b"}
    assert "a → b → a" in by_code(found, "GOAL_CYCLE").message


def test_a_thread_naming_a_goal_that_is_gone_is_reported_on_the_thread():
    """What a book written before goals were records looks like, until it is
    migrated. Said about the thread, because that is where the id is stored."""
    found = goal_findings([], [thread("road", ["s"], goals=["Win"])], {}, {"road": ["s"]})
    finding = by_code(found, "GOAL_UNKNOWN")
    assert finding.goal is None
    assert finding.plotlines == ("road",)
    assert "'Win'" in finding.message


def test_a_goal_achieved_at_a_scene_that_is_gone_is_a_fault():
    threads = [thread("road", ["s"], goals=["seal"])]
    found = goal_findings(
        [goal("seal", achieved_at="deleted")], threads, {"s": scene("s")}, {"road": ["s"]}
    )
    assert by_code(found, "GOAL_NOT_REACHED").severity == CONFLICT


# -- ordering ----------------------------------------------------------------


@pytest.mark.parametrize("order", [("a", "b"), ("b", "a")])
def test_findings_come_back_in_goal_order_whatever_order_they_went_in(order):
    """Two reads of one book say the same thing in the same order."""
    goals = [goal(gid) for gid in order]
    assert [f.goal for f in goal_findings(goals, [], {}, {})] == ["a", "a", "b", "b"]


# -- which scene delivers what ------------------------------------------------


def test_goals_by_event_is_achieved_at_read_backwards():
    goals = [goal("crown", achieved_at="coronation"), goal("seal", achieved_at="harbour")]
    assert {k: [g.id for g in v] for k, v in goals_by_event(goals).items()} == {
        "coronation": ["crown"], "harbour": ["seal"],
    }


def test_a_scene_can_deliver_several_goals():
    goals = [goal("b", achieved_at="e1"), goal("a", achieved_at="e1")]
    assert [g.id for g in goals_by_event(goals)["e1"]] == ["a", "b"]


def test_a_goal_with_no_scene_is_absent_rather_than_bucketed_under_none():
    """It has no place on a timeline, and the surfaces that care about it want
    it named separately -- not found under a key meaning "nowhere"."""
    assert goals_by_event([goal("someday")]) == {}


def test_the_order_within_a_scene_does_not_wobble_between_reads():
    """Two reads of one book must put the same goal first: an order that moves
    is one a reader notices and a test cannot pin."""
    forward = [goal("c", achieved_at="e1"), goal("a", achieved_at="e1"),
               goal("b", achieved_at="e1")]
    assert ([g.id for g in goals_by_event(forward)["e1"]]
            == [g.id for g in goals_by_event(list(reversed(forward)))["e1"]]
            == ["a", "b", "c"])


def test_no_goals_is_no_buckets():
    assert goals_by_event([]) == {}
