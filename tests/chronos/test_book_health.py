"""Unit tests for the whole-book continuity report (no DB, no Flask).

The rules themselves are tested next door, in ``test_plotline_health``. What is
interesting here is the *folding*: one problem seen from several threads must
come out as one issue that names them all, a scene on no thread must still be
looked at, and the number this report attributes to a thread must be the number
the plotline table already prints for it.
"""

from visualizer.chronos.book_health import Issue, book_issues
from visualizer.chronos.calendar import IdentityCodec
from visualizer.chronos.continuation import Resolution, resolve_all
from visualizer.chronos.models import EntityRef, Event, Plotline
from visualizer.chronos.plotline_health import CONFLICT, INFO, conflict_counts
from visualizer.chronos.presenters import present_book_report

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


def report(events, paths, terminus=None, missing_refs=(), resolutions=None):
    """The report for a book described as bare paths (or real resolutions)."""
    by_id = {e.id: e for e in events}
    if resolutions is None:
        resolutions = {pid: Resolution(events=list(p)) for pid, p in paths.items()}
    return book_issues(
        resolutions, by_id, CODEC, missing_refs=missing_refs, terminus=terminus
    )


def codes(issues):
    return sorted(i.code for i in issues)


def one(issues, code) -> Issue:
    found = [i for i in issues if i.code == code]
    assert len(found) == 1, f"expected exactly one {code}, got {codes(issues)}"
    return found[0]


# -- folding one problem out of many sightings -------------------------------


def test_a_pair_problem_is_one_issue_however_many_scenes_carry_it():
    # Reported on both scenes by the per-thread pass; one problem to a reader.
    events = [ev("a", 40, 50, title="Later"), ev("b", 0, 10, title="Earlier")]
    issues = report(events, {"pl": ["a", "b"]}, terminus="b")
    assert codes(issues) == ["ORDERING_VIOLATION"]


def test_an_issue_is_anchored_to_the_scene_its_message_is_about():
    events = [ev("a", 40, 50, title="Later"), ev("b", 0, 10, title="Earlier")]
    issue = one(report(events, {"pl": ["a", "b"]}), "ORDERING_VIOLATION")
    # "This scene..." only reads correctly beside the scene it is said about.
    assert issue.scene == "a"
    assert issue.message == "This scene has not ended when 'Earlier' begins."
    assert issue.events == ("b",)


def test_a_conflict_across_two_threads_names_both_of_them():
    events = [
        ev("a", 0, 24, "highkeep", ["aldric"]),
        ev("b", 10, 30, "emberport", ["aldric"]),
    ]
    issues = report(events, {"knights": ["a"], "spies": ["b"]})
    issue = one(issues, "TEMPORAL_CONFLICT")
    assert issue.plotlines == ("knights", "spies")
    # Both ends are named, whichever one the wording is anchored to.
    assert {issue.scene, *issue.events} == {"a", "b"}


def test_the_same_problem_on_one_thread_names_it_once():
    events = [
        ev("a", 0, 24, "highkeep", ["aldric"]),
        ev("b", 10, 30, "emberport", ["aldric"]),
    ]
    issue = one(report(events, {"both": ["a", "b"]}), "TEMPORAL_CONFLICT")
    assert issue.plotlines == ("both",)


def test_a_sound_book_reports_nothing():
    events = [ev("a", 0, 10, characters=["aldric"]), ev("b", 20, 30, characters=["lyra"])]
    assert report(events, {"pl": ["a", "b"]}, terminus="b") == []


# -- scenes on no thread -----------------------------------------------------


def test_a_scene_no_thread_uses_is_still_checked():
    # Written, never threaded -- invisible to every per-thread pass, and exactly
    # the scene a writer forgets they left contradicting the book.
    events = [
        ev("a", 0, 24, "highkeep", ["aldric"]),
        ev("orphan", 10, 30, "emberport", ["aldric"]),
    ]
    issue = one(report(events, {"pl": ["a"]}), "TEMPORAL_CONFLICT")
    assert {issue.scene, *issue.events} == {"a", "orphan"}
    # It belongs to the thread that can see it, and to no other.
    assert issue.plotlines == ("pl",)


def test_an_unthreaded_scene_alone_belongs_to_no_thread():
    events = [
        ev("x", 0, 24, "highkeep", ["aldric"]),
        ev("y", 10, 30, "emberport", ["aldric"]),
    ]
    issue = one(report(events, {}), "TEMPORAL_CONFLICT")
    assert issue.plotlines == ()


def test_two_unthreaded_scenes_are_not_judged_for_order():
    # They sit on no path, so there is no "before" to be wrong about.
    events = [ev("late", 40, 50), ev("early", 0, 10)]
    assert codes(report(events, {})) == []


# -- the ending --------------------------------------------------------------


def test_a_book_with_no_ending_says_so_once():
    issues = report([ev("a", 0, 10)], {"one": ["a"], "two": ["a"]})
    issue = one(issues, "NO_TERMINUS")
    # A book-wide fact, not one repeated at every thread.
    assert issue.plotlines == ()
    assert issue.severity == CONFLICT


def test_a_thread_that_stops_short_names_where_it_stops_and_where_it_should():
    events = [ev("a", 0, 10, title="Departure"), ev("t", 40, 50, title="The Coronation")]
    issues = report(events, {"knights": ["a"], "spies": ["a", "t"]}, terminus="t")
    issue = one(issues, "TERMINUS_VIOLATION")
    assert issue.plotlines == ("knights",)
    assert "'Departure'" in issue.message and "'The Coronation'" in issue.message
    assert issue.events == ("a",)  # so the report can offer a jump to it


def test_a_thread_with_no_scenes_is_a_problem_of_its_own():
    issues = report([ev("t", 0, 10)], {"empty": [], "real": ["t"]}, terminus="t")
    assert one(issues, "EMPTY_PLOTLINE").plotlines == ("empty",)


# -- broken continuations ----------------------------------------------------


def test_a_looping_continuation_is_reported_as_a_note_not_a_contradiction():
    # A write refuses to create one, so this is a state a book falls into
    # sideways -- and the plotline view already renders it as a hint.
    plotlines = [
        Plotline(id="one", events=["a"], goals=["g"], continues_into="two"),
        Plotline(id="two", events=["b"], goals=["g"], continues_into="one"),
    ]
    issues = report(
        [ev("a", 0, 10), ev("b", 20, 30)], {}, resolutions=resolve_all(plotlines)
    )
    loops = [i for i in issues if i.code == "PLOTLINE_CYCLE"]
    assert len(loops) == 2 and all(i.severity == INFO for i in loops)
    assert "one" in loops[0].message and "two" in loops[0].message


def test_a_continuation_into_nothing_is_reported_against_the_thread():
    plotlines = [Plotline(id="one", events=["a"], goals=["g"], continues_into="ghost")]
    issues = report([ev("a", 0, 10)], {}, resolutions=resolve_all(plotlines))
    issue = one(issues, "INVALID_PLOTLINE")
    assert issue.plotlines == ("one",) and "'ghost'" in issue.message


# -- severity ----------------------------------------------------------------


def test_an_undated_scene_is_a_note_and_a_scene_with_no_room_is_a_problem():
    constrained = [ev("a", 0, 10), ev("b", None, None), ev("c", 20, 30)]
    assert one(report(constrained, {"pl": ["a", "b", "c"]}), "UNSCHEDULED").severity == INFO

    boxed_in = [ev("a", 30, 40), ev("b", None, None), ev("c", 0, 10)]
    issues = report(boxed_in, {"pl": ["a", "b", "c"]})
    assert one(issues, "IMPOSSIBLE_WINDOW").severity == CONFLICT


def test_a_deleted_article_under_a_finished_scene_is_a_problem():
    gone = ref("aldric")
    issues = report(
        [ev("a", 0, 10, characters=["aldric"])], {"pl": ["a"]}, missing_refs=[gone]
    )
    issue = one(issues, "MISSING_ENTITY")
    assert issue.severity == CONFLICT and issue.refs == (gone,)


# -- ordering ----------------------------------------------------------------


def test_the_report_reads_in_story_order_with_undated_scenes_last():
    events = [
        ev("late", 100, 110, "highkeep", ["aldric"]),
        ev("late-clash", 100, 110, "emberport", ["aldric"]),
        ev("early", 0, 10, "highkeep", ["lyra"]),
        ev("early-clash", 0, 10, "emberport", ["lyra"]),
        ev("undated", None, None, "highkeep", ["bran"]),
        ev("undated-clash", None, None, "emberport", ["bran"]),
    ]
    paths = {"a": ["early", "late", "undated"],
             "b": ["early-clash", "late-clash", "undated-clash"]}
    anchors = [i.scene for i in report(events, paths) if i.code == "TEMPORAL_CONFLICT"]
    assert anchors[:2] == ["early", "late"]


# -- the invariant that matters ----------------------------------------------


def test_what_the_report_attributes_to_a_thread_is_what_the_table_prints():
    """The book report and the plotline table must never disagree about a thread.

    They are computed differently -- findings folded across the book vs. one
    counting pass over it -- and a writer sees both on adjacent screens. This
    holds the report to the number the table already shows.
    """
    events = [
        ev("a", 0, 24, "highkeep", ["aldric"]),
        ev("b", 10, 30, "emberport", ["aldric"]),   # conflicts with a
        ev("c", 40, 50, "highkeep", ["lyra"]),
        ev("d", 35, 45, "emberport", ["lyra"]),     # conflicts with c
        ev("late", 100, 110), ev("early", 0, 5),    # out of order when adjacent
        ev("undated", None, None),
        ev("orphan", 20, 25, "emberport", ["bran"]),  # on no thread at all
    ]
    by_id = {e.id: e for e in events}
    paths = {
        "one": ["a", "c"],
        "two": ["late", "early"],
        "three": ["late", "undated", "early"],
        "clean": ["c"],
    }
    issues = report(events, paths, terminus="early")
    # The table's number counts contradictions among the scenes on a thread; the
    # report adds the whole-thread verdicts (reaching the ending), which the
    # table has never shown, so those are excluded here.
    whole_thread = {"TERMINUS_VIOLATION", "EMPTY_PLOTLINE", "NO_TERMINUS"}
    mine = {
        pid: len([
            i for i in issues
            if i.severity == CONFLICT and pid in i.plotlines and i.code not in whole_thread
        ])
        for pid in paths
    }
    assert mine == conflict_counts(paths, by_id)


# -- presentation ------------------------------------------------------------


def presented(events, paths, **kwargs):
    plotlines = [Plotline(id=pid, events=list(p), goals=["g"]) for pid, p in paths.items()]
    return present_book_report(
        report(events, paths, **kwargs), {e.id: e for e in events}, plotlines
    )


def test_the_report_groups_problems_by_kind_and_counts_them():
    events = [
        ev("a", 0, 24, "highkeep", ["aldric"], title="The Vigil"),
        ev("b", 10, 30, "emberport", ["aldric"], title="The Ambush"),
    ]
    body = presented(events, {"pl": ["a", "b"]}, terminus="b")
    titles = [g["title"] for g in body["problems"]]
    assert titles == ["A character in two places at once", "Scenes out of order"]
    assert body["summary"]["problems"] == 2
    assert body["status"] == "conflicted"


def test_a_group_states_the_severity_its_rows_share():
    """So the view can mark the group once instead of every row in it.

    Safe only because severity follows the code and a group is one heading's
    worth of codes -- if that ever stops being true, a group would be claiming
    something about rows that disagree with it.
    """
    events = [ev("a", 0, 10), ev("b", None, None), ev("c", 20, 30),
              ev("d", 40, 50, "emberport", ["aldric"]),
              ev("e", 45, 55, "highkeep", ["aldric"])]
    body = presented(events, {"pl": ["a", "b", "c"], "other": ["d", "e"]}, terminus="c")
    for section, expected in (("problems", CONFLICT), ("notes", INFO)):
        assert body[section], f"expected a {section} group to check"
        for group in body[section]:
            assert group["severity"] == expected, group["title"]
            assert {i["severity"] for i in group["issues"]} == {expected}, group["title"]


def test_notes_are_kept_apart_from_problems():
    events = [ev("a", 0, 10), ev("b", None, None), ev("c", 20, 30)]
    body = presented(events, {"pl": ["a", "b", "c"]}, terminus="c")
    assert body["problems"] == []
    assert body["status"] == "consistent"  # a draft state is not a fault
    assert body["summary"]["unscheduled"] == 1
    assert body["notes"][0]["title"] == "Scenes still waiting for a time"


def test_a_presented_issue_names_its_scene_and_threads_by_title():
    events = [ev("a", 40, 50, title="Later"), ev("b", 0, 10, title="Earlier")]
    body = presented(events, {"pl": ["a", "b"]}, terminus="b")
    issue = body["problems"][0]["issues"][0]
    assert issue["scene"] == {"id": "a", "title": "Later"}
    assert issue["events"] == [{"id": "b", "title": "Earlier"}]
    assert issue["plotlines"] == [{"id": "pl", "title": "pl"}]
    assert issue["doc"].endswith("#52")


def test_the_rollup_counts_every_problem_that_names_a_thread():
    """The triage list must agree with the page it sits under.

    It is a *different* number from the plotline table's Health column -- it
    includes the whole-thread verdicts that column has never shown -- so what
    pins it is the report's own contents, not the table's.
    """
    events = [ev("a", 0, 10, title="Departure"), ev("t", 40, 50, title="The End")]
    body = presented(events, {"short": ["a"], "whole": ["a", "t"]}, terminus="t")
    named = {}
    for group in body["problems"]:
        for issue in group["issues"]:
            for pl in issue["plotlines"]:
                named[pl["id"]] = named.get(pl["id"], 0) + 1
    assert {p["id"]: p["problems"] for p in body["plotlines"]} == {
        "short": named.get("short", 0), "whole": named.get("whole", 0),
    }
    # 'short' stops at 'Departure' and never reaches the ending; 'whole' is sound.
    assert named == {"short": 1}


def test_every_thread_appears_in_the_rollup_even_when_sound():
    # It is the filter's menu as well as a triage list: a thread with nothing
    # wrong still has to be selectable.
    body = presented([ev("t", 0, 10)], {"clean": ["t"], "also": ["t"]}, terminus="t")
    assert [p["problems"] for p in body["plotlines"]] == [0, 0]
    assert {p["id"] for p in body["plotlines"]} == {"clean", "also"}


def test_both_kinds_of_broken_continuation_file_under_one_heading():
    plotlines = [
        Plotline(id="loop-a", events=["a"], goals=["g"], continues_into="loop-b"),
        Plotline(id="loop-b", events=["b"], goals=["g"], continues_into="loop-a"),
        Plotline(id="lost", events=["a"], goals=["g"], continues_into="ghost"),
    ]
    events = [ev("a", 0, 10), ev("b", 20, 30)]
    body = present_book_report(
        book_issues(resolve_all(plotlines), {e.id: e for e in events}, CODEC),
        {e.id: e for e in events},
        plotlines,
    )
    broken = [g for g in body["notes"] if g["title"] == "Broken continuations"]
    assert len(broken) == 1
    assert sorted(broken[0]["codes"]) == ["INVALID_PLOTLINE", "PLOTLINE_CYCLE"]
