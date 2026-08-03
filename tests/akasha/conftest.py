"""Shared test fixtures.

All database-touching tests run against an in-memory MongoDB provided by
``mongomock`` -- no real MongoDB server is ever contacted. The same in-memory
client backs both the document store and the auth store, mirroring production
where they share one MongoDB.
"""

import mongomock
import pytest
from werkzeug.security import generate_password_hash

from visualizer.akasha.app import create_app
from visualizer.akasha.auth_store import AuthStore
from visualizer.akasha.store import DocumentStore

DB = "testdb"
COLLECTION = "things"

ADMIN_USER = "admin"
ADMIN_PASS = "admin-pass"


@pytest.fixture
def mongo_client():
    """A fresh in-memory Mongo client per test (shared by both stores)."""
    return mongomock.MongoClient()


@pytest.fixture
def store(mongo_client):
    """Store with the default DB/COLLECTION already created."""
    s = DocumentStore(mongo_client)
    s.create_collection(DB, COLLECTION)
    return s


@pytest.fixture
def auth_store(mongo_client):
    """Auth store seeded with an admin account.

    Admins are no longer privileged over *content*: they must hold grants like
    anyone else. Most HTTP tests use the admin as a convenient omnipotent actor,
    so the seeded admin is given an instance-wide grant (an admin who has granted
    themselves full access). Tests that exercise the deny-by-default behaviour
    build their own ungranted admin.
    """
    s = AuthStore(mongo_client)
    s.create_user(ADMIN_USER, generate_password_hash(ADMIN_PASS), role="admin")
    s.grant_owner(ADMIN_USER, None, None, None, ["read", "write", "delete"])
    return s


@pytest.fixture
def app(store, auth_store):
    app = create_app(store, auth_store, secret_key="test-secret")
    # CSRF is exercised in the browser; disable it so API-style tests stay terse.
    # Rate limiting is exercised by a dedicated test; off here so the many
    # per-test logins don't trip the per-IP limits.
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    return app


def login(client, username, password):
    """Authenticate a test client (JSON login sets the session cookie)."""
    return client.post("/login", json={"username": username, "password": password})


@pytest.fixture
def anon_client(app):
    """An unauthenticated test client."""
    return app.test_client()


@pytest.fixture
def client(app):
    """A Flask test client authenticated as the seeded admin."""
    c = app.test_client()
    resp = login(c, ADMIN_USER, ADMIN_PASS)
    assert resp.status_code == 200
    return c


def register(client, username, password, email=None):
    return client.post(
        "/register",
        json={
            "username": username,
            "password": password,
            "email": email or f"{username}@example.com",
        },
    )


def collection_url(database=DB, collection=COLLECTION):
    return f"/databases/{database}/collections/{collection}"


def doc_url(doc_id, database=DB, collection=COLLECTION):
    return f"/databases/{database}/collections/{collection}/documents/{doc_id}"


def search_url(database=DB, collection=COLLECTION):
    return f"/databases/{database}/collections/{collection}/search"
