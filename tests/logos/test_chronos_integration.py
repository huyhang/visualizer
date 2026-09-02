"""Chronos protects the book and the scenes that Logos prose is written from.

These exercise the Chronos *services*, not its routes. That is the point: the
guard lives in the service, so it holds for the standalone Chronos entrypoint
and for any caller, not only for the combined gateway where the wiring happens.
"""

import pytest

from visualizer.chronos.entity_gate import FakeEntityGate
from visualizer.chronos.errors import EventInManuscript, ManuscriptInUse
from visualizer.chronos.models import Book, EntityRef, Event
from visualizer.chronos.services import BookService, EventService
from visualizer.chronos.store import CalendarStore, StoryStore
from visualizer.logos.gateways import LogosReferenceGate

from .conftest import BOOK, SECTION, VOLUME, section_payload


def _stories(mongo_client):
    stories = StoryStore(mongo_client)
    stories.create_book(BOOK, Book(BOOK, title="The Ember Pact").to_storage(), "mara")
    event = Event("opening", EntityRef("ember", "locations", "gate"), 0, 1,
                  title="Opening")
    stories.create_event(BOOK, event.id, event.to_storage(), "mara")
    return stories


def _manuscript(logos_store):
    logos_store.create_outline(BOOK, {"volumes": [VOLUME]}, "mara")
    logos_store.create_volume(
        BOOK, VOLUME, {"title": "One", "overview": "", "sections": [SECTION]}, "mara"
    )
    logos_store.create_section(BOOK, VOLUME, SECTION, section_payload(), "mara")


def test_a_book_whose_manuscript_holds_prose_cannot_be_deleted(
    mongo_client, logos_store
):
    _manuscript(logos_store)
    stories = _stories(mongo_client)
    books = BookService(
        stories,
        FakeEntityGate(),
        CalendarStore(mongo_client),
        LogosReferenceGate(logos_store),
    )

    with pytest.raises(ManuscriptInUse):
        books.delete(BOOK, expected_rev=1, author="mara")

    assert stories.get_book(BOOK)["title"] == "The Ember Pact"


def test_a_scene_a_section_is_written_from_cannot_be_deleted(
    mongo_client, logos_store
):
    _manuscript(logos_store)
    stories = _stories(mongo_client)
    events = EventService(
        stories, FakeEntityGate(), LogosReferenceGate(logos_store)
    )

    with pytest.raises(EventInManuscript) as blocked:
        events.delete(BOOK, "opening", expected_rev=1, author="mara")

    assert blocked.value.evidence == {
        "sections": [{"volume": VOLUME, "section": SECTION}]
    }
    assert stories.get_event(BOOK, "opening")["title"] == "Opening"


def test_detach_cannot_be_used_to_talk_past_the_manuscript(
    mongo_client, logos_store
):
    """``detach=true`` clears plotline references. It must not clear prose."""
    _manuscript(logos_store)
    events = EventService(
        _stories(mongo_client), FakeEntityGate(), LogosReferenceGate(logos_store)
    )

    with pytest.raises(EventInManuscript):
        events.delete(BOOK, "opening", expected_rev=1, author="mara", detach=True)


def test_a_scene_named_only_by_an_older_revision_is_free_to_go(
    mongo_client, logos_store
):
    """History is not a live reference. Restoring that revision later is what
    revalidates the scene -- and fails then if it really has gone."""
    _manuscript(logos_store)
    logos_store.update_section(
        BOOK, VOLUME, SECTION, section_payload(events=()), 1, "mara"
    )
    stories = _stories(mongo_client)
    events = EventService(
        stories, FakeEntityGate(), LogosReferenceGate(logos_store)
    )

    events.delete(BOOK, "opening", expected_rev=1, author="mara")

    assert stories.list_events(BOOK) == []


def test_chronos_without_a_manuscript_service_behaves_exactly_as_before(
    mongo_client, logos_store
):
    """The null gate is the default, so an installation with no Logos attached
    keeps the delete semantics it has always had."""
    _manuscript(logos_store)
    stories = _stories(mongo_client)
    unguarded = BookService(stories, FakeEntityGate(), CalendarStore(mongo_client))

    unguarded.delete(BOOK, expected_rev=1, author="mara")

    assert stories.list_books() == []


def test_a_book_that_has_no_manuscript_still_deletes_cleanly(
    mongo_client, logos_store
):
    stories = _stories(mongo_client)
    guarded = BookService(
        stories,
        FakeEntityGate(),
        CalendarStore(mongo_client),
        LogosReferenceGate(logos_store),
    )

    guarded.delete(BOOK, expected_rev=1, author="mara")

    assert stories.list_books() == []
