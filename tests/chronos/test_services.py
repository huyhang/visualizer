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
    RevisionConflict,
    TerminusInUse,
)
from visualizer.chronos.models import Plotline
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
    by_id = {e["id"]: e for e in expanded["effective_events"]}
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


# -- deleting a book ---------------------------------------------------------


def test_deleting_a_book_cascades_to_its_plotlines_and_events(svc):
    svc["events"].create(BOOK, "a", _event())
    svc["plotlines"].create(BOOK, "p1", {"events": ["a"], "goals": ["g"]})
    svc["books"].delete(BOOK)
    assert svc["books"].list() == []
    # Not merely unreachable through the book -- actually gone from the store.
    assert svc["plotlines"].store.list_plotlines(BOOK) == []
    assert svc["events"].store.list_events(BOOK) == []


def test_a_stale_delete_leaves_the_book_and_its_story_intact(svc):
    """The precondition is checked before the cascade, not by the last write in
    it. There is no transaction to roll back, so "refused" has to mean nothing
    happened rather than everything but the book."""
    svc["events"].create(BOOK, "a", _event())
    svc["plotlines"].create(BOOK, "p1", {"events": ["a"], "goals": ["g"]})
    svc["books"].update(BOOK, {"title": "Renamed"})  # the book is now at rev 2

    with pytest.raises(RevisionConflict):
        svc["books"].delete(BOOK, expected_rev=1)

    assert svc["books"].get(BOOK)["title"] == "Renamed"
    assert svc["plotlines"].get(BOOK, "p1")["events"] == ["a"]
    assert svc["events"].get(BOOK, "a")["id"] == "a"


# -- the overview survives the writes nobody asked for -----------------------
#
# Three service operations rewrite a *whole* stored document as a side effect of
# doing something else. That is how a field added later gets quietly dropped:
# the writer edits nothing, and their prose is gone. One test per site -- and
# then one more that does not name a field at all, so the next field added is
# covered before anyone thinks to test it.

PROSE = "Two sisters, and the winter between them."


def _stored_plotline(svc, plotline_id):
    return svc["plotlines"].store.get_plotline(BOOK, plotline_id)


# The store stamps these on every write; they are expected to move.
_STORE_OWNED = {"rev", "updated_by"}


@pytest.mark.parametrize("rewrite,may_change", [
    ("detach", {"events"}),
    ("inline", {"events", "continues_into"}),
], ids=["detach", "inline"])
def test_a_side_effect_rewrite_changes_only_what_it_is_about(svc, rewrite, may_change):
    """The guard that outlives this feature.

    Asserting "the overview survived" only ever covers the field you happened to
    be thinking about. This inverts it: the operation declares the short list of
    fields it is *allowed* to move, and every other stored field must come out
    byte-identical. A field added later is covered without anyone remembering to
    cover it -- dropping it shows up as an unexpected change.

    Checking values, not keys: a rebuild that forgets a field still writes the
    key, because ``to_storage`` always emits it. It writes the *default*, which
    is precisely the silent loss being guarded against.
    """
    svc["events"].create(BOOK, "a", _event("highkeep", 0, 10))
    svc["events"].create(BOOK, "b", _event("highkeep", 20, 30))
    svc["events"].create(BOOK, "spare", _event("highkeep", 40, 50))
    svc["plotlines"].create(BOOK, "tail", {"events": ["b"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "p1", {
        "events": ["a", "spare"], "goals": ["g"], "title": "A Distinctive Title",
        "continues_into": "tail", "overview": PROSE,
    })
    before = _stored_plotline(svc, "p1")

    # Meta-check: every field the model defines must hold a non-default value
    # above, or this guard would quietly stop covering it. Whoever adds the next
    # field gets a failure here telling them to give it a value.
    defaults = Plotline(id="p1", events=before["events"], goals=before["goals"]).to_storage()
    unset = [k for k, v in defaults.items() if k not in ("events", "goals") and before[k] == v]
    assert not unset, f"give {unset} a distinctive value here so the guard covers it"

    if rewrite == "detach":
        svc["events"].delete(BOOK, "spare", detach=True)
    else:
        svc["plotlines"].inline(BOOK, "p1")

    after = _stored_plotline(svc, "p1")
    changed = {
        k for k in set(before) | set(after)
        if before.get(k) != after.get(k)
    } - _STORE_OWNED
    assert changed == may_change, (
        f"the {rewrite} rewrite should touch {sorted(may_change)}, "
        f"but changed {sorted(changed)}"
    )


def test_overview_survives_detaching_a_deleted_scene(svc):
    """``EventService.delete(detach=True)`` rewrites every thread that listed
    the scene."""
    svc["events"].create(BOOK, "a", _event("highkeep", 0, 10))
    svc["events"].create(BOOK, "b", _event("highkeep", 20, 30))
    svc["plotlines"].create(
        BOOK, "p1", {"events": ["a", "b"], "goals": ["g"], "overview": PROSE},
    )
    svc["events"].delete(BOOK, "a", detach=True)
    after = svc["plotlines"].get(BOOK, "p1")
    assert after["events"] == ["b"]
    assert after["overview"] == PROSE


def test_overview_survives_inlining_a_continuation(svc):
    """``PlotlineService.inline`` rebuilds the thread from a fresh model."""
    svc["events"].create(BOOK, "a", _event("highkeep", 0, 10))
    svc["events"].create(BOOK, "t", _event("highkeep", 20, 30))
    svc["plotlines"].create(BOOK, "trunk", {"events": ["t"], "goals": ["g"]})
    svc["plotlines"].create(BOOK, "p1", {
        "events": ["a"], "goals": ["g"], "continues_into": "trunk", "overview": PROSE,
    })
    inlined = svc["plotlines"].inline(BOOK, "p1")
    assert inlined["events"] == ["a", "t"], "expected the chain to be absorbed"
    assert inlined["overview"] == PROSE


def test_overview_survives_designating_a_terminus(svc):
    """``BookService.set_terminus`` is a full book write with one field changed."""
    svc["books"].update(BOOK, {"title": "The Ember Pact", "overview": PROSE})
    svc["events"].create(BOOK, "t", _event())
    assert svc["books"].set_terminus(BOOK, "t")["overview"] == PROSE


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
