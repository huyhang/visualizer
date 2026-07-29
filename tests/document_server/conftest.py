"""Shared test fixtures.

All database-touching tests run against an in-memory MongoDB provided by
``mongomock`` -- no real MongoDB server is ever contacted. The same in-memory
client backs both the document store and the auth store, mirroring production
where they share one MongoDB.
"""

import mongomock
import pytest
from werkzeug.security import generate_password_hash

from visualizer.document_server.app import create_app
from visualizer.document_server.auth_store import AuthStore
from visualizer.document_server.store import DocumentStore

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
    """Auth store seeded with a single admin account."""
    s = AuthStore(mongo_client)
    s.create_user(ADMIN_USER, generate_password_hash(ADMIN_PASS), role="admin")
    return s


@pytest.fixture
def app(store, auth_store):
    app = create_app(store, auth_store, secret_key="test-secret")
    # CSRF is exercised in the browser; disable it so API-style tests stay terse.
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
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
