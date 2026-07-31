"""Shared fixtures for Chronos tests.

DB-touching tests use an in-memory ``mongomock`` client (never a real Mongo) and
a fixed clock, mirroring the injected-seam design. The same client can back both
the Chronos store and a akasha ``DocumentStore`` -- exactly as
production shares one Mongo.
"""

from datetime import datetime, timezone

import mongomock
import pytest
from werkzeug.security import generate_password_hash

from visualizer.akasha.auth_store import AuthStore
from visualizer.akasha.store import DocumentStore
from visualizer.chronos.app import create_app
from visualizer.chronos.entity_gate import FakeEntityGate, InProcessEntityGate
from visualizer.chronos.models import EntityRef
from visualizer.chronos.store import StoryStore

FIXED_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)

ADMIN_USER = "admin"
ADMIN_PASS = "admin-pass"
WRITER = "mara"
WRITER_PASS = "mara-pass"


@pytest.fixture
def mongo_client():
    return mongomock.MongoClient()


@pytest.fixture
def story_store(mongo_client):
    return StoryStore(mongo_client, clock=lambda: FIXED_TIME)


@pytest.fixture
def doc_store(mongo_client):
    """A akasha store sharing the same Mongo, for entity checks."""
    return DocumentStore(mongo_client)


@pytest.fixture
def inprocess_gate(doc_store):
    return InProcessEntityGate(doc_store)


@pytest.fixture
def fake_gate():
    return FakeEntityGate()


@pytest.fixture
def auth_store(mongo_client):
    s = AuthStore(mongo_client)
    s.create_user(ADMIN_USER, generate_password_hash(ADMIN_PASS), role="admin")
    s.create_user(WRITER, generate_password_hash(WRITER_PASS), role="user")
    return s


@pytest.fixture
def app(story_store, fake_gate, auth_store):
    application = create_app(story_store, fake_gate, auth_store, secret_key="test-secret")
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def _login(client, username, password):
    return client.post("/login", json={"username": username, "password": password})


@pytest.fixture
def client(app):
    """A test client authenticated as a plain writer (owns what they create)."""
    c = app.test_client()
    assert _login(c, WRITER, WRITER_PASS).status_code == 200
    return c


@pytest.fixture
def admin_client(app):
    """A client authenticated as an admin (bypasses grant checks)."""
    c = app.test_client()
    assert _login(c, ADMIN_USER, ADMIN_PASS).status_code == 200
    return c


def ref(id_, collection="characters", database="ember-pact"):
    return EntityRef(database, collection, id_)
