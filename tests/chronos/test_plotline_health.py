"""Unit tests for the per-scene findings the editor marks up (no DB, no Flask).

These are the same three rules ``/validate`` reports book-wide, asked per scene
on one thread -- so the interesting cases are about *attribution* (which scene
gets marked, and what it says) as much as detection.
"""

from visualizer.chronos.calendar import IdentityCodec
from visualizer.chronos.models import EntityRef, Event
from visualizer.chronos.ordering import all_violations, validate_order
from visualizer.chronos.plotline_health import (
    CONFLICT,
    INFO,
    conflict_count,
    findings_for_path,
)

CODEC = IdentityCodec()


def ref(id_, collection="characters"):
    return EntityRef("ember-pact", collection, id_)


def ev(id_, start, end, location="highkeep", characters=(), title=None):
    return Event(
        id=id_,
        title=title,
        location=ref(location, "locations"),
        start_tick=start,
        end_tick=end,
        characters=[ref(c) for c in characters],
    )


def findings(path, events, paths=None):
    by_id = {e.id: e for e in events}
    return findings_for_path(path, by_id, paths or {"pl": list(path)}, CODEC)


def codes(found, event_id):
    return [f.code for f in found.get(event_id, [])]


# -- ordering: every violation, on both ends ---------------------------------


def test_reports_every_out_of_order_pair_not_just_the_first():
    # Both adjacent pairs run backwards; validate_order stops at the first.
    events = [ev("a", 40, 50), ev("b", 20, 30), ev("c", 0, 10)]
    assert validate_order(events).before_id == "a"
    assert [(v.before_id, v.after_id) for v in all_violations(events)] == [("a", "b"), ("b", "c")]


def test_ordering_violation_marks_both_scenes_from_each_point_of_view():
    found = findings(["a", "b"], [ev("a", 40, 50, title="Later"), ev("b", 0, 10, title="Earlier")])
    assert codes(found, "a") == ["ORDERING_VIOLATION"]
    assert codes(found, "b") == ["ORDERING_VIOLATION"]
    # Phrased for the row the writer is looking at, and naming the other scene.
    assert found["b"][0].message == "'Later' has not ended when this scene begins."
    assert found["a"][0].message == "This scene has not ended when 'Earlier' begins."
    assert found["a"][0].events == ("b",)


def test_touching_scenes_are_in_order():
    # Half-open intervals: end == start is allowed (design 4).
    assert findings(["a", "b"], [ev("a", 0, 10), ev("b", 10, 20)]) == {}


def test_unscheduled_scene_between_two_ordered_ones_is_not_a_violation():
    events = [ev("a", 0, 10), ev("b", None, None), ev("c", 20, 30)]
    assert "ORDERING_VIOLATION" not in codes(findings(["a", "b", "c"], events), "b")


# -- temporal conflicts ------------------------------------------------------


def test_marks_the_scene_that_puts_a_character_in_two_places():
    events = [ev("a", 0, 24, "highkeep", ["aldric"]), ev("b", 10, 30, "emberport", ["aldric"])]
    found = findings(["a", "b"], events)
    # Overlapping scenes in sequence are out of order too, so both rules fire --
    # what matters here is that the conflict is attributed to both ends.
    assert "TEMPORAL_CONFLICT" in codes(found, "a")
    assert "TEMPORAL_CONFLICT" in codes(found, "b")
    conflict = found["a"][0]
    assert conflict.events == ("b",)
    assert "aldric" in conflict.message
    assert conflict.severity == CONFLICT


def test_conflict_with_a_scene_on_another_thread_is_still_reported_here():
    # 'other' is not on this path at all, but the writer still needs to know:
    # the contradiction is visible from the thread they are editing.
    events = [
        ev("a", 0, 24, "highkeep", ["aldric"]),
        ev("other", 10, 30, "emberport", ["aldric"]),
    ]
    found = findings(["a"], events, paths={"pl": ["a"], "elsewhere": ["other"]})
    assert codes(found, "a") == ["TEMPORAL_CONFLICT"]
    assert "other" not in found  # only scenes on this path are marked


def test_same_location_overlap_is_not_a_conflict():
    events = [ev("a", 0, 24, "highkeep", ["aldric"]), ev("b", 10, 30, "highkeep", ["aldric"])]
    assert "TEMPORAL_CONFLICT" not in codes(findings(["a", "b"], events), "a")


# -- timing hints ------------------------------------------------------------


def test_impossible_window_is_a_conflict_on_the_undated_scene():
    # 'b' must start after 40 and end before 10: no room at all.
    events = [ev("a", 30, 40), ev("b", None, None), ev("c", 0, 10)]
    found = findings(["a", "b", "c"], events)
    assert codes(found, "b") == ["IMPOSSIBLE_WINDOW"]
    assert found["b"][0].severity == CONFLICT
    assert "start after 40" in found["b"][0].message
    assert "end before 0" in found["b"][0].message


def test_constrained_undated_scene_gets_an_informational_hint():
    events = [ev("a", 0, 10), ev("b", None, None), ev("c", 20, 30)]
    found = findings(["a", "b", "c"], events)
    assert codes(found, "b") == ["UNSCHEDULED"]
    assert found["b"][0].severity == INFO
    assert "between 10 and 20" in found["b"][0].message


def test_unconstrained_undated_scene_says_nothing():
    # "No timing yet" is a draft state, not a problem: marking every unplaced
    # scene would train the writer to ignore the markers.
    assert findings(["b"], [ev("b", None, None)]) == {}


def test_window_hint_uses_the_only_bound_it_has():
    after_only = findings(["a", "b"], [ev("a", 0, 10), ev("b", None, None)])
    assert "after 10" in after_only["b"][0].message
    before_only = findings(["b", "c"], [ev("b", None, None), ev("c", 20, 30)])
    assert "before 20" in before_only["b"][0].message


def test_window_accounts_for_every_thread_the_scene_appears_on():
    # 'b' is undated on two threads; the tighter bound from the other one wins.
    events = [ev("a", 0, 10), ev("b", None, None), ev("c", 90, 99), ev("d", 20, 30)]
    found = findings(
        ["a", "b", "c"], events, paths={"pl": ["a", "b", "c"], "other": ["b", "d"]}
    )
    assert "between 10 and 20" in found["b"][0].message


# -- counting ----------------------------------------------------------------


def test_a_pair_problem_counts_once_though_both_scenes_are_marked():
    found = findings(["a", "b"], [ev("a", 40, 50), ev("b", 0, 10)])
    assert len(found) == 2
    assert conflict_count(found) == 1


def test_informational_findings_do_not_count_as_conflicts():
    found = findings(["a", "b", "c"], [ev("a", 0, 10), ev("b", None, None), ev("c", 20, 30)])
    assert codes(found, "b") == ["UNSCHEDULED"]
    assert conflict_count(found) == 0


def test_a_sound_thread_has_no_findings():
    events = [ev("a", 0, 10, characters=["aldric"]), ev("b", 20, 30, characters=["lyra"])]
    assert findings(["a", "b"], events) == {}
    assert conflict_count({}) == 0


# -- naming Akasha articles --------------------------------------------------


def test_conflict_quotes_every_article_id_so_a_client_can_swap_in_titles():
    # The ids are quoted on purpose: a UI replaces "'aldric'" with "'Sir Aldric'"
    # by exact match, which a bare substring could not do safely.
    events = [
        ev("a", 0, 24, "highkeep", ["aldric", "lyra"]),
        ev("b", 10, 30, "emberport", ["aldric", "lyra"]),
    ]
    finding = findings(["a", "b"], events)["a"][0]
    assert "'aldric' and 'lyra'" in finding.message
    assert "'emberport'" in finding.message


def test_conflict_carries_the_articles_it_names():
    # Titles live in Akasha, which this module cannot see -- so it hands over the
    # refs and lets a client that holds the grant resolve them.
    events = [ev("a", 0, 24, "highkeep", ["aldric"]), ev("b", 10, 30, "emberport", ["aldric"])]
    finding = findings(["a", "b"], events)["a"][0]
    assert finding.refs == (ref("aldric"), ref("emberport", "locations"))


def test_findings_with_nothing_to_resolve_carry_no_refs():
    ordering = findings(["a", "b"], [ev("a", 40, 50), ev("b", 0, 10)])["a"][0]
    assert ordering.code == "ORDERING_VIOLATION"
    assert ordering.refs == ()


# -- counting the whole book at once -----------------------------------------


def test_one_pass_counting_agrees_with_counting_thread_by_thread():
    """The table and the plotline view must never disagree about a thread.

    They are computed differently now -- one pass over the book vs. per-path
    findings -- so this holds the fast path to the careful one.
    """
    from visualizer.chronos.plotline_health import conflict_counts

    events = [
        ev("a", 0, 24, "highkeep", ["aldric"]),
        ev("b", 10, 30, "emberport", ["aldric"]),   # conflicts with a
        ev("c", 40, 50, "highkeep", ["lyra"]),
        ev("d", 35, 45, "emberport", ["lyra"]),     # conflicts with c
        ev("late", 100, 110), ev("early", 0, 5),    # out of order when adjacent
        ev("undated", None, None),
    ]
    by_id = {e.id: e for e in events}
    paths = {
        "one": ["a", "c"],                    # each end of a different conflict
        "two": ["late", "early"],             # an ordering violation
        "three": ["late", "undated", "early"],  # ...and no room for the undated one
        "clean": ["c"],
    }
    fast = conflict_counts(paths, by_id)
    careful = {
        pid: conflict_count(findings_for_path(path, by_id, paths, CODEC))
        for pid, path in paths.items()
    }
    assert fast == careful
    assert fast["two"] == 1 and fast["three"] >= 2 and fast["one"] == 2


def test_one_pass_counting_sees_a_conflict_from_either_end():
    from visualizer.chronos.plotline_health import conflict_counts

    events = [ev("a", 0, 24, "highkeep", ["aldric"]), ev("b", 10, 30, "emberport", ["aldric"])]
    by_id = {e.id: e for e in events}
    # Whichever end of the pair a thread contains, it has one problem -- and a
    # thread containing both still has one, not two.
    counts = conflict_counts({"x": ["a"], "y": ["b"], "both": ["a", "b"]}, by_id)
    assert counts == {"x": 1, "y": 1, "both": 2}  # 'both' adds its ordering break
