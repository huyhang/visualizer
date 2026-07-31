"""Tests for the StoryStore seam and the EntityGate adapters (mongomock)."""

import pytest

from tests.chronos.conftest import ref
from visualizer.chronos.errors import (
    AlreadyExists,
    BookNotFound,
    EventNotFound,
    RevisionConflict,
)

BOOK = "ember-pact"


def _event_body(location="highkeep", start=0, end=10, characters=()):
    return {
        "title": None,
        "location": ref(location, "locations").to_dict(),
        "start_tick": start,
        "end_tick": end,
        "description": "",
        "characters": [ref(c).to_dict() for c in characters],
        "items": [],
    }


# -- CRUD + OCC --------------------------------------------------------------


def test_create_and_get_book(story_store):
    created = story_store.create_book(BOOK, {"title": "The Ember Pact"}, author="mara")
    assert created["id"] == BOOK
    assert created["rev"] == 1
    assert created["created_by"] == "mara"
    fetched = story_store.get_book(BOOK)
    assert fetched["title"] == "The Ember Pact"


def test_create_duplicate_raises(story_store):
    story_store.create_book(BOOK, {"title": "x"})
    with pytest.raises(AlreadyExists):
        story_store.create_book(BOOK, {"title": "y"})


def test_get_missing_raises(story_store):
    with pytest.raises(BookNotFound):
        story_store.get_book("nope")


def test_update_bumps_rev_and_author(story_store):
    story_store.create_book(BOOK, {"title": "x"}, author="mara")
    updated = story_store.update_book(BOOK, {"title": "y"}, expected_rev=1, author="finn")
    assert updated["rev"] == 2
    assert updated["title"] == "y"
    assert updated["created_by"] == "mara" and updated["updated_by"] == "finn"


def test_stale_rev_conflicts(story_store):
    story_store.create_book(BOOK, {"title": "x"})
    story_store.update_book(BOOK, {"title": "y"}, expected_rev=1)
    with pytest.raises(RevisionConflict):
        story_store.update_book(BOOK, {"title": "z"}, expected_rev=1)


def test_delete_then_recreate(story_store):
    story_store.create_event(BOOK, "e1", _event_body())
    story_store.delete_event(BOOK, "e1")
    with pytest.raises(EventNotFound):
        story_store.get_event(BOOK, "e1")
    # id may be reused after a hard delete
    story_store.create_event(BOOK, "e1", _event_body(start=5, end=6))
    assert story_store.get_event(BOOK, "e1")["start_tick"] == 5


def test_books_are_scoped(story_store):
    story_store.create_event("book-a", "e1", _event_body())
    story_store.create_event("book-b", "e1", _event_body(start=99, end=100))
    assert story_store.get_event("book-a", "e1")["start_tick"] == 0
    assert story_store.get_event("book-b", "e1")["start_tick"] == 99
    assert len(story_store.list_events("book-a")) == 1


# -- targeted queries --------------------------------------------------------


def test_events_involving_filters_by_character(story_store):
    story_store.create_event(BOOK, "e1", _event_body(characters=["aldric"]))
    story_store.create_event(BOOK, "e2", _event_body(characters=["lyra"]))
    story_store.create_event(BOOK, "e3", _event_body(characters=["aldric", "lyra"]))
    got = story_store.events_involving(BOOK, [ref("aldric").to_dict()])
    assert {e["id"] for e in got} == {"e1", "e3"}


def test_events_involving_empty_refs(story_store):
    story_store.create_event(BOOK, "e1", _event_body(characters=["aldric"]))
    assert story_store.events_involving(BOOK, []) == []


def test_get_events_preserves_order_and_skips_missing(story_store):
    for eid, start in [("a", 0), ("b", 10), ("c", 20)]:
        story_store.create_event(BOOK, eid, _event_body(start=start, end=start + 1))
    got = story_store.get_events(BOOK, ["c", "a", "ghost"])
    assert [e["id"] for e in got] == ["c", "a"]


# -- entity gate -------------------------------------------------------------


def test_inprocess_gate_against_document_store(doc_store, inprocess_gate):
    doc_store.create_collection("ember-pact", "characters")
    doc_store.create("ember-pact", "characters", "aldric", {"title": "Sir Aldric"})
    assert inprocess_gate.exists(ref("aldric")) is True
    assert inprocess_gate.exists(ref("ghost")) is False


def test_gate_missing_reports_absent_refs(doc_store, inprocess_gate):
    doc_store.create_collection("ember-pact", "characters")
    doc_store.create("ember-pact", "characters", "aldric", {"title": "Sir Aldric"})
    missing = inprocess_gate.missing([ref("aldric"), ref("ghost"), ref("ghost")])
    assert missing == [ref("ghost")]  # deduped, only the absent one


def test_fake_gate(fake_gate):
    fake_gate.add(ref("aldric"))
    assert fake_gate.exists(ref("aldric"))
    assert fake_gate.missing([ref("aldric"), ref("lyra")]) == [ref("lyra")]
