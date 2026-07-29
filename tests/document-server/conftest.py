"""Shared test fixtures.

All database-touching tests run against an in-memory MongoDB provided by
``mongomock`` -- no real MongoDB server is ever contacted.
"""

import mongomock
import pytest

from app import create_app
from store import DocumentStore


@pytest.fixture
def mongo_client():
    """A fresh in-memory Mongo client per test."""
    return mongomock.MongoClient()


DB = "testdb"
COLLECTION = "things"


@pytest.fixture
def store(mongo_client):
    """Store with the default DB/COLLECTION already created.

    Document operations now require an existing namespace, so the default one is
    created up front; tests that exercise the "namespace missing" path use other
    names.
    """
    s = DocumentStore(mongo_client)
    s.create_collection(DB, COLLECTION)
    return s


@pytest.fixture
def client(store):
    """A Flask test client wired to the in-memory store."""
    app = create_app(store)
    app.config.update(TESTING=True)
    return app.test_client()


def collection_url(database=DB, collection=COLLECTION):
    return f"/databases/{database}/collections/{collection}"


def doc_url(doc_id, database=DB, collection=COLLECTION):
    return f"/databases/{database}/collections/{collection}/documents/{doc_id}"


def search_url(database=DB, collection=COLLECTION):
    return f"/databases/{database}/collections/{collection}/search"
