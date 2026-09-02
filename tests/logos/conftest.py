"""Shared in-memory fixtures for Logos: no real Mongo, no network, fixed clock."""

from datetime import UTC, datetime

import mongomock
import pytest
from werkzeug.security import generate_password_hash

from visualizer.auth import ALL_PERMS, AuthStore
from visualizer.logos.app import BOOK_RESOURCE, create_app
from visualizer.logos.gateways import FakeArticleGateway, FakeChronosGateway
from visualizer.logos.store import LogosStore

BOOK = "ember-pact"
VOLUME = "the-ember-pact"
SECTION = "the-broken-gate"
WORLD = "ember"
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def paragraph(text: str, node_id: str) -> dict:
    content = [{"type": "text", "text": text}] if text else []
    return {"type": "paragraph", "id": node_id, "content": content}


def document(*texts: str) -> dict:
    return {
        "version": 1,
        "type": "doc",
        "content": [paragraph(text, f"p{n}") for n, text in enumerate(texts, 1)],
    }


def mention(article: str, text: str, node_id: str = "p1") -> dict:
    """A one-paragraph document whose prose mentions an Akasha article."""
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "id": node_id,
                "content": [
                    {
                        "type": "mention",
                        "ref": {
                            "database": WORLD,
                            "collection": "characters",
                            "id": article,
                        },
                        "text": text,
                    }
                ],
            }
        ],
    }


def section_payload(kind="chapter", title="The Broken Gate", events=("opening",),
                    doc=None):
    return {
        "kind": kind,
        "title": title,
        "overview": "Lyra reaches the gate.",
        "event_ids": list(events),
        "document": doc if doc is not None else document("The gate was open."),
    }


@pytest.fixture
def mongo_client():
    return mongomock.MongoClient()


@pytest.fixture
def logos_store(mongo_client):
    return LogosStore(
        mongo_client, section_revisions_keep=20, clock=lambda: FIXED_TIME
    )


@pytest.fixture
def chronos_gateway():
    gateway = FakeChronosGateway()
    gateway.add_book(BOOK, "The Ember Pact", events=("opening", "climax"))
    return gateway


@pytest.fixture
def article_gateway():
    return FakeArticleGateway([(WORLD, "characters", "lyra")])


@pytest.fixture
def auth_store(mongo_client):
    store = AuthStore(mongo_client)
    store.create_user("mara", generate_password_hash("mara-pass"), role="user")
    store.create_user("devi", generate_password_hash("devi-pass"), role="user")
    store.grant_owner(
        "mara", BOOK, None, None, list(ALL_PERMS), resource_type=BOOK_RESOURCE
    )
    store.add_grant(
        "devi", BOOK, None, None, ["read"], "mara", resource_type=BOOK_RESOURCE
    )
    return store


@pytest.fixture
def app(logos_store, chronos_gateway, article_gateway, auth_store):
    application = create_app(
        logos_store,
        chronos_gateway,
        article_gateway,
        auth_store,
        secret_key="test-secret",
        akasha_url="/",
    )
    application.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False
    )
    return application


def login(client, username="mara"):
    return client.post(
        "/login", json={"username": username, "password": f"{username}-pass"}
    )


@pytest.fixture
def client(app):
    """Signed in as the book's owner."""
    test_client = app.test_client()
    assert login(test_client).status_code == 200
    return test_client


@pytest.fixture
def reader(app):
    """Signed in as a collaborator holding 'read' and nothing more."""
    test_client = app.test_client()
    assert login(test_client, "devi").status_code == 200
    return test_client


@pytest.fixture
def volume(client):
    response = client.post(
        f"/books/{BOOK}/volumes/{VOLUME}",
        json={"title": "The Ember Pact", "overview": "Volume one."},
    )
    assert response.status_code == 201, response.get_json()
    return client


@pytest.fixture
def section(volume):
    response = volume.post(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}", json=section_payload()
    )
    assert response.status_code == 201, response.get_json()
    return volume
