"""Logos behind the single origin: one login, and the cross-service guards live.

This is the only test that assembles the real four-app stack. It exists because
every other test injects a fake somewhere, and the wiring itself -- which app is
mounted where, which gateway each one actually received -- is exactly what a
fake cannot check.
"""

import json

from werkzeug.test import Client

from visualizer.akasha.app import create_app as create_akasha_app
from visualizer.akasha.store import DocumentStore
from visualizer.chronos.app import create_app as create_chronos_app
from visualizer.chronos.entity_gate import FakeEntityGate
from visualizer.chronos.models import Book, EntityRef, Event
from visualizer.chronos.store import CalendarStore, StoryStore
from visualizer.gateway import DEFAULT_LOGOS_PREFIX, combine
from visualizer.logos.app import create_app as create_logos_app
from visualizer.logos.gateways import (
    InProcessArticleGateway,
    InProcessChronosGateway,
    LogosReferenceGate,
)
from visualizer.logos.store import LogosStore

from .conftest import BOOK, section_payload

SHARED = {
    "secret_key": "test-secret",
    "akasha_url": "/",
    "chronos_url": "/timeline",
    "prithvi_url": "/prithvi",
}


def _body(response):
    return json.loads(response.get_data(as_text=True))


def _stack(mongo_client, auth_store):
    documents = DocumentStore(mongo_client)
    stories = StoryStore(mongo_client)
    stories.create_book(BOOK, Book(BOOK, title="The Ember Pact").to_storage(), "mara")
    opening = Event("opening", EntityRef("ember", "locations", "gate"), 0, 1)
    stories.create_event(BOOK, opening.id, opening.to_storage(), "mara")
    logos_store = LogosStore(mongo_client)

    apps = (
        create_akasha_app(documents, auth_store, **SHARED),
        create_chronos_app(
            stories,
            FakeEntityGate(),
            auth_store,
            calendar_store=CalendarStore(mongo_client),
            manuscript_gate=LogosReferenceGate(logos_store),
            **SHARED,
        ),
        create_logos_app(
            logos_store,
            InProcessChronosGateway(stories),
            InProcessArticleGateway(documents),
            auth_store,
            **SHARED,
        ),
    )
    for app in apps:
        app.config.update(
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False
        )
    return Client(combine(apps[0], apps[1], logos_app=apps[2]))


def test_one_login_reaches_logos_and_chronos_then_refuses_to_orphan_prose(
    mongo_client, auth_store
):
    client = _stack(mongo_client, auth_store)

    assert client.get(DEFAULT_LOGOS_PREFIX + "/health").status_code == 200
    assert client.post(
        "/login", json={"username": "mara", "password": "mara-pass"}
    ).status_code == 200

    manuscript = client.get(DEFAULT_LOGOS_PREFIX + f"/books/{BOOK}")
    assert manuscript.status_code == 200
    assert _body(manuscript)["title"] == "The Ember Pact"

    assert client.post(
        DEFAULT_LOGOS_PREFIX + f"/books/{BOOK}/volumes/one", json={"title": "One"}
    ).status_code == 201
    assert client.post(
        DEFAULT_LOGOS_PREFIX + f"/books/{BOOK}/volumes/one/sections/opening",
        json=section_payload(),
    ).status_code == 201

    blocked_book = client.delete(
        f"/timeline/books/{BOOK}", headers={"If-Match": '"1"'}
    )
    blocked_event = client.delete(
        f"/timeline/books/{BOOK}/events/opening", headers={"If-Match": '"1"'}
    )

    assert _body(blocked_book)["code"] == "MANUSCRIPT_IN_USE"
    assert _body(blocked_event)["code"] == "EVENT_IN_MANUSCRIPT"


def test_the_akasha_gateway_logos_receives_is_the_real_document_store(
    mongo_client, auth_store
):
    """A mention resolves or does not according to Akasha itself, not a copy."""
    client = _stack(mongo_client, auth_store)
    client.post("/login", json={"username": "mara", "password": "mara-pass"})
    client.post(DEFAULT_LOGOS_PREFIX + f"/books/{BOOK}/volumes/one",
                json={"title": "One"})

    ref = {"database": "ember", "collection": "characters", "id": "lyra"}
    prose = {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "id": "p1",
                "content": [{"type": "mention", "ref": ref, "text": "Lyra"}],
            }
        ],
    }
    created = client.post(
        DEFAULT_LOGOS_PREFIX + f"/books/{BOOK}/volumes/one/sections/opening",
        json=section_payload(events=(), doc=prose),
    )

    assert created.status_code == 201
    assert _body(created)["missing_refs"] == [ref]
