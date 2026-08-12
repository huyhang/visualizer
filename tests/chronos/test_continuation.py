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


def pl(pid, events, continues_into=None):
    return Plotline(pid, events, ["g"], continues_into=continues_into)


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
