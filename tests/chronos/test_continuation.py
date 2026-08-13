"""Plotline continuations: a shared ending stored once (design §3.3).

Covers the pure resolver (chains, cycles, dangling targets), the hard rejects at
the service layer, and the end-to-end behaviour through the API.
"""

import pytest

from tests.chronos.conftest import ref
from visualizer.chronos.book_rules import graph_view, validate_convergence
from visualizer.chronos.continuation import (
    effective_paths,
    resolve,
    resolve_all,
    would_cycle,
)
from visualizer.chronos.errors import InvalidPlotline, PlotlineCycle, PlotlineInUse
from visualizer.chronos.models import Plotline
from visualizer.chronos.services import BookService, EventService, PlotlineService

BOOK = "ember-pact"


def pl(pid, events, continues_into=None, continues_into_at=None):
    return Plotline(pid, events, ["g"], continues_into=continues_into,
                    continues_into_at=continues_into_at)


# -- the pure resolver -------------------------------------------------------


def test_resolves_a_single_hop():
    pls = [pl("trunk", ["m", "t"]), pl("knights", ["a"], "trunk")]
    r = resolve("knights", {p.id: p for p in pls})
    assert r.ok
    assert r.events == ["a", "m", "t"]
    assert r.chain == ["knights", "trunk"]


def test_resolves_a_multi_hop_chain():
    pls = [pl("c", ["z"]), pl("b", ["y"], "c"), pl("a", ["x"], "b")]
    r = resolve("a", {p.id: p for p in pls})
    assert r.events == ["x", "y", "z"]
    assert r.chain == ["a", "b", "c"]


def test_plotline_without_continuation_is_unchanged():
    r = resolve("solo", {"solo": pl("solo", ["a", "b"])})
    assert r.ok and r.events == ["a", "b"] and r.chain == ["solo"]


def test_cycle_is_reported_not_hung():
    pls = [pl("a", ["x"], "b"), pl("b", ["y"], "a")]
    r = resolve("a", {p.id: p for p in pls})
    assert not r.ok
    assert r.cycle == ["a", "b", "a"]


def test_self_reference_cycle():
    r = resolve("a", {"a": pl("a", ["x"], "a")})
    assert r.cycle == ["a", "a"]


def test_dangling_continuation_is_reported():
    r = resolve("a", {"a": pl("a", ["x"], "ghost")})
    assert not r.ok
    assert r.missing == "ghost"


def test_would_cycle_detects_a_closing_loop():
    existing = [pl("trunk", ["m", "t"]), pl("knights", ["a"], "trunk")]
    # trunk continuing back into knights would close the loop
    assert would_cycle(pl("trunk", ["m", "t"], "knights"), existing) is not None
    assert would_cycle(pl("spies", ["b"], "trunk"), existing) is None


def test_resolve_all_covers_every_plotline():
    pls = [pl("trunk", ["m", "t"]), pl("knights", ["a"], "trunk")]
    assert {k: v.events for k, v in resolve_all(pls).items()} == {
        "trunk": ["m", "t"],
        "knights": ["a", "m", "t"],
    }


# -- joining partway down the target (``continues_into_at``) ----------------------


def test_joins_the_target_at_a_named_scene():
    """The point of the feature: pick the trunk up halfway, not at its head."""
    pls = [pl("trunk", ["m1", "m2", "t"]), pl("late", ["a"], "trunk", "m2")]
    r = resolve("late", {p.id: p for p in pls})
    assert r.ok
    assert r.events == ["a", "m2", "t"], "the trunk's opening is not inherited"


def test_joining_at_the_targets_first_scene_matches_joining_at_the_head():
    pls = [pl("trunk", ["m", "t"]), pl("named", ["a"], "trunk", "m"),
           pl("unnamed", ["a"], "trunk")]
    by_id = {p.id: p for p in pls}
    assert resolve("named", by_id).events == resolve("unnamed", by_id).events


def test_joining_at_the_last_scene_inherits_only_that_scene():
    pls = [pl("trunk", ["m", "t"]), pl("late", ["a"], "trunk", "t")]
    assert resolve("late", {p.id: p for p in pls}).events == ["a", "t"]


def test_join_scene_missing_from_the_target_is_reported():
    """Reachable without touching this thread -- the trunk can drop the scene."""
    pls = [pl("trunk", ["m", "t"]), pl("late", ["a"], "trunk", "gone")]
    r = resolve("late", {p.id: p for p in pls})
    assert not r.ok
    assert r.anchor_missing == "gone"


def test_join_scene_may_live_further_down_the_chain():
    """``continues_into_at`` names a scene on the target's *resolved* path.

    'tail' is not stored on 'mid' at all, but a writer looking at 'mid' sees it,
    so it must be joinable.
    """
    pls = [pl("last", ["t"]), pl("mid", ["m"], "last"), pl("early", ["a"], "mid", "t")]
    assert resolve("early", {p.id: p for p in pls}).events == ["a", "t"]


def test_joins_compose_along_a_multi_hop_chain():
    pls = [
        pl("last", ["x", "y", "z"]),
        pl("mid", ["m"], "last", "y"),      # mid  -> [m, y, z]
        pl("early", ["a"], "mid", "z"),     # early-> [a, z]
    ]
    by_id = {p.id: p for p in pls}
    assert resolve("mid", by_id).events == ["m", "y", "z"]
    assert resolve("early", by_id).events == ["a", "z"]


def test_effective_paths_reflect_the_join_point():
    pls = [pl("trunk", ["m1", "m2", "t"]), pl("late", ["a"], "trunk", "m2")]
    assert effective_paths(pls) == {
        "trunk": ["m1", "m2", "t"],
        "late": ["a", "m2", "t"],
    }


def test_two_threads_may_join_one_trunk_at_different_points():
    """The shape a real book has: a trunk several threads meet at, each where
    its own story catches up. Checked through ``resolve_all``, because that is
    what every rule and the graph actually consume."""
    pls = [pl("trunk", ["m1", "m2", "m3", "t"]),
           pl("early", ["a"], "trunk", "m1"),
           pl("late", ["b"], "trunk", "m3")]
    assert {k: v.events for k, v in resolve_all(pls).items()} == {
        "trunk": ["m1", "m2", "m3", "t"],
        "early": ["a", "m1", "m2", "m3", "t"],
        "late": ["b", "m3", "t"],
    }


def test_an_anchor_the_target_itself_sliced_off_is_reported():
    """The subtle one, and the reason resolution folds from the tail back.

    'y' exists, and it is in 'c' -- but 'b' joins 'c' at 'z', so 'y' is *not*
    on the path 'b' presents. A resolver that searched the target's stored
    segment, or the book at large, would happily join at a scene the thread it
    is joining cannot reach.
    """
    pls = [pl("c", ["x", "y", "z"]), pl("b", ["m"], "c", "z"), pl("a", ["n"], "b", "y")]
    r = resolve("a", {p.id: p for p in pls})
    assert not r.ok and r.anchor_missing == "y"


def test_a_one_scene_trunk_can_still_be_joined_at_that_scene():
    pls = [pl("trunk", ["t"]), pl("j", ["a"], "trunk", "t")]
    assert resolve("j", {p.id: p for p in pls}).events == ["a", "t"]


def test_a_cycle_through_a_join_point_is_still_reported():
    pls = [pl("a", ["x"], "b", "y"), pl("b", ["y"], "a", "x")]
    assert resolve("a", {p.id: p for p in pls}).cycle == ["a", "b", "a"]


# -- rules run on the resolved path ------------------------------------------


def test_a_thread_converges_through_its_continuation():
    """The whole point: knights never lists 't', but still reaches it."""
    pls = [pl("trunk", ["m", "t"]), pl("knights", ["a"], "trunk"), pl("spies", ["b"], "trunk")]
    report = validate_convergence(effective_paths(pls), "t")
    assert report.ok, report.failures


def test_a_broken_chain_fails_convergence_for_every_thread_on_it():
    pls = [pl("trunk", ["m", "x"]), pl("knights", ["a"], "trunk")]  # trunk misses 't'
    report = validate_convergence(effective_paths(pls), "t")
    assert {f["plotline"] for f in report.failures} == {"trunk", "knights"}


def test_graph_includes_the_junction_edge():
    pls = [pl("trunk", ["m", "t"]), pl("knights", ["a"], "trunk")]
    view = graph_view(effective_paths(pls), "t")
    edges = {(e["from"], e["to"]) for e in view["edges"]}
    assert ("a", "m") in edges, "junction into the continuation must be an edge"


def test_shared_tail_is_a_convergence_point():
    pls = [pl("trunk", ["m", "t"]), pl("knights", ["a"], "trunk"), pl("spies", ["b"], "trunk")]
    view = graph_view(effective_paths(pls), "t")
    assert view["convergence"] == ["m"]


# -- service layer: hard rejects ---------------------------------------------


@pytest.fixture
def svc(story_store, fake_gate, calendar_store):
    fake_gate.add(ref("aldric"))
    fake_gate.add(ref("highkeep", "locations"))
    books = BookService(story_store, fake_gate, calendar_store)
    books.create(BOOK, {"title": "The Ember Pact"})
    events = EventService(story_store, fake_gate)
    for eid, s, e in [("a", 0, 10), ("b", 0, 10), ("m", 20, 30), ("t", 40, 50)]:
        events.create(BOOK, eid, {
            "location": ref("highkeep", "locations").to_dict(),
            "start_tick": s, "end_tick": e,
            "characters": [ref("aldric").to_dict()],
        })
    return {"books": books, "events": events,
            "plotlines": PlotlineService(story_store, fake_gate)}


def test_continuation_to_unknown_plotline_is_rejected(svc):
    with pytest.raises(InvalidPlotline) as ei:
        svc["plotlines"].create(BOOK, "knights",
                                {"events": ["a"], "goals": ["g"], "continues_into": "ghost"})
    assert ei.value.evidence["continues_into"] == "ghost"


def test_cycle_is_rejected(svc):
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "knights",
                            {"events": ["a"], "goals": ["g"], "continues_into": "trunk"})
    with pytest.raises(PlotlineCycle) as ei:
        svc["plotlines"].update(BOOK, "trunk",
                                {"events": ["m", "t"], "goals": ["g"], "continues_into": "knights"})
    assert "trunk" in ei.value.evidence["cycle"]


def test_self_continuation_is_rejected(svc):
    with pytest.raises(InvalidPlotline):
        svc["plotlines"].create(BOOK, "knights",
                                {"events": ["a"], "goals": ["g"], "continues_into": "knights"})


def test_shared_tail_end_to_end(svc):
    """Three threads, one shared ending, written once."""
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    for pid, first in (("knights", "a"), ("spies", "b")):
        svc["plotlines"].create(BOOK, pid,
                                {"events": [first], "goals": ["g"], "continues_into": "trunk"})
    svc["books"].set_terminus(BOOK, "t")
    assert svc["books"].validate(BOOK)["status"] == "consistent"

    got = svc["plotlines"].get(BOOK, "knights")
    assert got["events"] == ["a"]                                    # stored segment
    assert got["effective_events"] == ["a", "m", "t"]                # resolved path
    assert got["continues_into"] == "trunk"
    assert got["status"]["ends_at_terminus"]["state"] == "ok"
    assert got["status"]["continuation"]["state"] == "ok"


def test_editing_the_trunk_updates_every_thread(svc):
    """The reason for the feature: no edit amplification on the shared tail."""
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    for pid, first in (("knights", "a"), ("spies", "b")):
        svc["plotlines"].create(BOOK, pid,
                                {"events": [first], "goals": ["g"], "continues_into": "trunk"})
    svc["books"].set_terminus(BOOK, "t")

    # insert a new scene into the shared ending -- touching only the trunk
    svc["events"].create(BOOK, "vigil", {
        "location": ref("highkeep", "locations").to_dict(),
        "start_tick": 32, "end_tick": 36,
        "characters": [ref("aldric").to_dict()],
    })
    current = svc["plotlines"].get(BOOK, "trunk")
    svc["plotlines"].update(BOOK, "trunk",
                            {"events": ["m", "vigil", "t"], "goals": ["g"]}, current["rev"])

    for pid in ("knights", "spies"):
        assert "vigil" in svc["plotlines"].get(BOOK, pid)["effective_events"]
    assert svc["books"].validate(BOOK)["status"] == "consistent"


def test_ordering_is_checked_across_the_junction(svc):
    """A thread whose segment ends after its continuation starts is reported."""
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    # 't' (40-50) ends after 'm' (20-30) begins -> junction is out of order
    got = svc["plotlines"].create(
        BOOK, "late", {"events": ["t"], "goals": ["g"], "continues_into": "trunk"}
    )
    assert got["status"]["ordering"]["state"] == "conflicted"


# -- service layer: joining partway down --------------------------------------


def test_join_at_a_scene_the_target_does_not_have_is_rejected(svc):
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    with pytest.raises(InvalidPlotline) as ei:
        svc["plotlines"].create(BOOK, "late", {
            "events": ["a"], "goals": ["g"],
            "continues_into": "trunk", "continues_into_at": "b",   # 'b' exists, not on trunk
        })
    assert ei.value.evidence["continues_into_at"] == "b"


def test_join_point_without_a_target_is_rejected(svc):
    with pytest.raises(InvalidPlotline):
        svc["plotlines"].create(
            BOOK, "late", {"events": ["a"], "goals": ["g"], "continues_into_at": "m"}
        )


def test_mid_trunk_join_end_to_end(svc):
    """A thread that catches the trunk at its last scene, not its first."""
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "late", {
        "events": ["a"], "goals": ["g"], "continues_into": "trunk", "continues_into_at": "t",
    })
    svc["books"].set_terminus(BOOK, "t")

    got = svc["plotlines"].get(BOOK, "late")
    assert got["events"] == ["a"]                       # stored segment, unchanged
    assert got["effective_events"] == ["a", "t"]        # 'm' is not inherited
    assert got["continues_into_at"] == "t"
    assert got["status"]["continuation"]["state"] == "ok"
    assert got["status"]["ordering"]["state"] == "ok"
    assert svc["books"].validate(BOOK)["status"] == "consistent"


def test_ordering_is_checked_against_the_joined_at_scene(svc):
    """The junction rule follows the join point, with no rule of its own.

    'b' (0-10) ends before 'm' (20-30), so joining the trunk at its head is
    sound; joining at 't' (40-50) is too. But a segment ending at 'm' and
    joining back at 'm' puts the same scene twice -- the ordering rule catches
    it because it reads the resolved path.
    """
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    sound = svc["plotlines"].create(BOOK, "sound", {
        "events": ["b"], "goals": ["g"], "continues_into": "trunk", "continues_into_at": "t",
    })
    assert sound["status"]["ordering"]["state"] == "ok"

    doubled = svc["plotlines"].create(BOOK, "doubled", {
        "events": ["b", "m"], "goals": ["g"], "continues_into": "trunk", "continues_into_at": "m",
    })
    assert doubled["effective_events"] == ["b", "m", "m", "t"]
    assert doubled["status"]["ordering"]["state"] == "conflicted"


def test_dropping_the_joined_at_scene_reports_the_thread_as_conflicted(svc):
    """Nobody writes 'late', but the trunk moving out from under it is visible."""
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "late", {
        "events": ["a"], "goals": ["g"], "continues_into": "trunk", "continues_into_at": "m",
    })
    current = svc["plotlines"].get(BOOK, "trunk")
    svc["plotlines"].update(
        BOOK, "trunk", {"events": ["t"], "goals": ["g"]}, current["rev"]
    )

    status = svc["plotlines"].get(BOOK, "late")["status"]["continuation"]
    assert status["state"] == "conflicted"
    assert status["evidence"]["anchor_missing"] == "m"


def test_the_continuation_target_is_named_as_well_as_identified(svc):
    """A reader showing "continues into <x>" holds an id; the slug is not what
    the writer called the thread, and fetching the target just to name it would
    be a round trip for a label."""
    svc["plotlines"].create(
        BOOK, "trunk", {"title": "The Road to the Crown", "events": ["m", "t"], "goals": ["g"]}
    )
    got = svc["plotlines"].create(BOOK, "knights", {
        "events": ["a"], "goals": ["g"], "continues_into": "trunk",
    })
    assert got["continues_into"] == "trunk"
    assert got["continues_into_title"] == "The Road to the Crown"


def test_an_untitled_target_is_named_by_its_id(svc):
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    got = svc["plotlines"].create(BOOK, "knights", {
        "events": ["a"], "goals": ["g"], "continues_into": "trunk",
    })
    assert got["continues_into_title"] == "trunk"


def test_a_thread_that_ends_on_its_own_names_nothing(svc):
    got = svc["plotlines"].create(BOOK, "solo", {"events": ["a", "t"], "goals": ["g"]})
    assert got["continues_into"] is None and got["continues_into_title"] is None


def test_a_dangling_target_is_not_given_a_title(svc):
    """The break is reported by ``status.continuation``; echoing the id back as
    a title would dress it up as working."""
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "knights", {
        "events": ["a"], "goals": ["g"], "continues_into": "trunk",
    })
    # Reached through the store, because the service refuses to orphan a thread
    # (PLOTLINE_IN_USE) -- which is the point: this state is not one a caller can
    # create, only one a reader may find.
    svc["plotlines"].store.delete_plotline(BOOK, "trunk", None, None)

    got = svc["plotlines"].get(BOOK, "knights")
    assert got["continues_into"] == "trunk"
    assert got["continues_into_title"] is None
    assert got["status"]["continuation"]["state"] == "conflicted"


def test_inline_collapses_a_chain_whose_every_hop_is_anchored(svc):
    """Inline is defined as a change of representation, not of content -- and a
    multi-hop chain with a join point at *each* hop is where that is easiest to
    get wrong: the absorbed path must be the sliced one, not the flattened one.
    """
    svc["plotlines"].create(BOOK, "last", {"events": ["m", "t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "mid", {
        "events": ["b"], "goals": ["g"], "continues_into": "last", "continues_into_at": "t",
    })
    svc["plotlines"].create(BOOK, "first", {
        "events": ["a"], "goals": ["g"], "continues_into": "mid", "continues_into_at": "t",
    })
    before = svc["plotlines"].get(BOOK, "first")["effective_events"]
    assert before == ["a", "t"], "'b' and 'm' are both before the junctions"

    out = svc["plotlines"].inline(BOOK, "first")
    assert out["events"] == before, "the exact story it had, written out flat"
    assert out["continues_into"] is None and out["continues_into_at"] is None


def test_inline_absorbs_the_sliced_path_and_clears_the_join(svc):
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "late", {
        "events": ["a"], "goals": ["g"], "continues_into": "trunk", "continues_into_at": "t",
    })
    out = svc["plotlines"].inline(BOOK, "late")
    assert out["events"] == ["a", "t"], "the story it had, not the trunk's opening"
    assert out["continues_into"] is None
    assert out["continues_into_at"] is None


# -- detaching: inline the chain (POST .../inline) ---------------------------


def _shared_tail(svc):
    svc["plotlines"].create(BOOK, "trunk", {"events": ["m", "t"], "goals": ["g"]})
    for pid, first in (("knights", "a"), ("spies", "b")):
        svc["plotlines"].create(BOOK, pid,
                                {"events": [first], "goals": ["g"], "continues_into": "trunk"})
    svc["books"].set_terminus(BOOK, "t")


def test_inline_keeps_the_story_and_drops_the_dependency(svc):
    _shared_tail(svc)
    out = svc["plotlines"].inline(BOOK, "knights")
    assert out["continues_into"] is None
    assert out["events"] == ["a", "m", "t"]          # absorbed, now standalone
    assert out["effective_events"] == ["a", "m", "t"]
    assert out["status"]["ends_at_terminus"]["state"] == "ok"
    assert svc["books"].validate(BOOK)["status"] == "consistent"


def test_inline_leaves_other_threads_alone(svc):
    _shared_tail(svc)
    svc["plotlines"].inline(BOOK, "knights")
    spies = svc["plotlines"].get(BOOK, "spies")
    assert spies["continues_into"] == "trunk"        # still sharing
    assert spies["effective_events"] == ["b", "m", "t"]


def test_inline_is_a_no_op_without_a_continuation(svc):
    _shared_tail(svc)
    once = svc["plotlines"].inline(BOOK, "knights")
    twice = svc["plotlines"].inline(BOOK, "knights")
    assert twice["events"] == once["events"]
    assert twice["rev"] == once["rev"], "a no-op must not bump the revision"


def test_inline_collapses_a_multi_hop_chain(svc):
    svc["plotlines"].create(BOOK, "last", {"events": ["t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "mid",
                            {"events": ["m"], "goals": ["g"], "continues_into": "last"})
    svc["plotlines"].create(BOOK, "first",
                            {"events": ["a"], "goals": ["g"], "continues_into": "mid"})
    out = svc["plotlines"].inline(BOOK, "first")
    assert out["events"] == ["a", "m", "t"] and out["continues_into"] is None


# -- deleting a plotline others depend on ------------------------------------


def test_deleting_a_depended_on_plotline_is_blocked(svc):
    _shared_tail(svc)
    with pytest.raises(PlotlineInUse) as ei:
        svc["plotlines"].delete(BOOK, "trunk")
    assert ei.value.evidence["plotlines"] == ["knights", "spies"]


def test_delete_with_inline_preserves_dependent_stories(svc):
    _shared_tail(svc)
    svc["plotlines"].delete(BOOK, "trunk", inline_dependents=True)
    for pid in ("knights", "spies"):
        got = svc["plotlines"].get(BOOK, pid)
        assert got["continues_into"] is None
        assert got["effective_events"][-1] == "t", "story must survive the deletion"
    assert svc["books"].validate(BOOK)["status"] == "consistent"


def test_deleting_an_independent_plotline_still_works(svc):
    _shared_tail(svc)
    svc["plotlines"].create(BOOK, "loner", {"events": ["a", "t"], "goals": ["g"]})
    svc["plotlines"].delete(BOOK, "loner")   # nothing depends on it
    assert "loner" not in svc["books"].get(BOOK)["plotlines"]
