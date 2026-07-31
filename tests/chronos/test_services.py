"""Service-layer tests: fake EntityGate + real (mongomock) StoryStore.

Assert orchestration -- entity checks, soft story-logic reporting, referential
hard rules, OCC flow -- without a Flask layer.
"""

import pytest

from tests.chronos.conftest import ref
from visualizer.chronos.errors import (
    EntityNotFound,
    EventInUse,
    InvalidPlotline,
    InvalidTimeframe,
    TerminusInUse,
)
from visualizer.chronos.services import BookService, EventService, PlotlineService

BOOK = "ember-pact"


@pytest.fixture
def svc(story_store, fake_gate):
    # Seed the entities Chronos will reference.
    for c in ("aldric", "lyra"):
        fake_gate.add(ref(c))
    for loc in ("highkeep", "emberport", "throne-hall"):
        fake_gate.add(ref(loc, "locations"))
    books = BookService(story_store, fake_gate)
    books.create(BOOK, {"title": "The Ember Pact"})
    return {
        "books": books,
        "events": EventService(story_store, fake_gate),
        "plotlines": PlotlineService(story_store, fake_gate),
        "gate": fake_gate,
    }


def _event(location="highkeep", start=0, end=10, characters=("aldric",)):
    return {
        "location": ref(location, "locations").to_dict(),
        "start_tick": start,
        "end_tick": end,
        "characters": [ref(c).to_dict() for c in characters],
    }


# -- events ------------------------------------------------------------------


def test_create_event_ok(svc):
    result = svc["events"].create(BOOK, "e1", _event())
    assert result["id"] == "e1" and result["rev"] == 1
    assert result["start_label"] == "0"  # identity codec (no calendar)


def test_create_event_rejects_missing_entity(svc):
    payload = _event(characters=("ghost",))
    with pytest.raises(EntityNotFound) as ei:
        svc["events"].create(BOOK, "e1", payload)
    assert ei.value.evidence["missing"][0]["id"] == "ghost"


def test_create_event_rejects_bad_timeframe(svc):
    with pytest.raises(InvalidTimeframe):
        svc["events"].create(BOOK, "e1", _event(start=10, end=5))


def test_temporal_conflict_is_soft(svc):
    # Two events, same character, different locations, overlapping -> a conflict,
    # but BOTH writes succeed (all-soft) and the book status turns conflicted.
    svc["events"].create(BOOK, "e1", _event("highkeep", 0, 24, ("aldric",)))
    svc["events"].create(BOOK, "e2", _event("emberport", 10, 30, ("aldric",)))
    report = svc["books"].validate(BOOK)
    assert report["status"] == "conflicted"
    assert len(report["temporal_conflicts"]) == 1


# -- plotlines ---------------------------------------------------------------


def test_plotline_rejects_unknown_event(svc):
    with pytest.raises(InvalidPlotline):
        svc["plotlines"].create(BOOK, "p1", {"events": ["ghost"], "goals": ["g"]})


def test_plotline_ordering_is_soft_and_reported(svc):
    svc["events"].create(BOOK, "a", _event("highkeep", 0, 72))
    svc["events"].create(BOOK, "b", _event("highkeep", 0, 48))
    pl = svc["plotlines"].create(BOOK, "p1", {"events": ["a", "b"], "goals": ["g"]})
    assert pl["status"]["ordering"]["state"] == "conflicted"
    assert pl["status"]["ordering"]["code"] == "ORDERING_VIOLATION"


def test_plotline_expand_marks_convergence(svc):
    for eid, s, e in [("a", 0, 10), ("b", 0, 10), ("m", 20, 30), ("t", 40, 50)]:
        svc["events"].create(BOOK, eid, _event("highkeep", s, e))
    svc["plotlines"].create(BOOK, "p1", {"events": ["a", "m", "t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "p2", {"events": ["b", "m", "t"], "goals": ["g"]})
    expanded = svc["plotlines"].get(BOOK, "p1", expand=True)
    by_id = {e["id"]: e for e in expanded["events"]}
    assert by_id["m"]["is_convergence"] is True
    assert by_id["m"]["shared_with"] == ["p2"]


# -- deletion semantics (§7.2) -----------------------------------------------


def test_delete_referenced_event_blocked(svc):
    svc["events"].create(BOOK, "a", _event())
    svc["plotlines"].create(BOOK, "p1", {"events": ["a"], "goals": ["g"]})
    with pytest.raises(EventInUse) as ei:
        svc["events"].delete(BOOK, "a")
    assert ei.value.evidence["plotlines"] == ["p1"]


def test_delete_with_detach_removes_from_plotlines(svc):
    svc["events"].create(BOOK, "a", _event("highkeep", 0, 10))
    svc["events"].create(BOOK, "b", _event("highkeep", 20, 30))
    svc["plotlines"].create(BOOK, "p1", {"events": ["a", "b"], "goals": ["g"]})
    svc["events"].delete(BOOK, "a", detach=True)
    assert svc["plotlines"].get(BOOK, "p1")["events"] == ["b"]


def test_delete_terminus_blocked(svc):
    svc["events"].create(BOOK, "t", _event())
    svc["books"].set_terminus(BOOK, "t")
    with pytest.raises(TerminusInUse):
        svc["events"].delete(BOOK, "t", detach=True)


# -- terminus / convergence --------------------------------------------------


def test_set_terminus_and_converge(svc):
    for eid, s, e in [("a", 0, 10), ("b", 0, 10), ("t", 40, 50)]:
        svc["events"].create(BOOK, eid, _event("highkeep", s, e))
    svc["plotlines"].create(BOOK, "p1", {"events": ["a", "t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "p2", {"events": ["b", "t"], "goals": ["g"]})
    svc["books"].set_terminus(BOOK, "t")
    assert svc["books"].validate(BOOK)["status"] == "consistent"


def test_neighborhood_convergence(svc):
    for eid, s, e in [("a", 0, 10), ("b", 0, 10), ("m", 20, 30), ("t", 40, 50)]:
        svc["events"].create(BOOK, eid, _event("highkeep", s, e))
    svc["plotlines"].create(BOOK, "p1", {"events": ["a", "m", "t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "p2", {"events": ["b", "m", "t"], "goals": ["g"]})
    n = svc["events"].neighborhood(BOOK, "m")
    assert n["role"] == "convergence"
    assert n["converging"]["is_convergence"] is True
    froms = {g["from"]["id"] for g in n["converging"]["incoming"]}
    assert froms == {"a", "b"}
