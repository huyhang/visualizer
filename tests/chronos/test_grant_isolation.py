"""Grants must not leak between services sharing one `_auth` store.

Regression tests for the bug where a chronos book grant was written as a
document-server *database* grant: creating a book named "x" silently conferred
read/write/delete on a document-server database also named "x".
"""

import pytest
from werkzeug.security import generate_password_hash

from visualizer.chronos.app import BOOK_RESOURCE
from visualizer.document_server.app import create_app as create_docs_app
from visualizer.document_server.authz import is_allowed
from visualizer.document_server.store import DocumentStore

# The collision case: a book and a document-server database with the SAME name.
SHARED_NAME = "ember-pact"
WRITER = "mara"
WRITER_PASS = "mara-pass"


@pytest.fixture
def docs_app(mongo_client, auth_store):
    store = DocumentStore(mongo_client)
    store.create_collection(SHARED_NAME, "characters")
    store.create("ember-pact", "characters", "aldric", {"title": "Sir Aldric"})
    app = create_docs_app(store, auth_store, secret_key="test-secret")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def _login(client, username=WRITER, password=WRITER_PASS):
    return client.post("/login", json={"username": username, "password": password})


def test_book_grant_does_not_grant_document_database(app, docs_app):
    """Creating a chronos book must not unlock the like-named docs database."""
    chronos = app.test_client()
    assert _login(chronos).status_code == 200
    assert chronos.post(f"/books/{SHARED_NAME}", json={"title": "x"}).status_code == 201

    docs = docs_app.test_client()
    assert _login(docs).status_code == 200
    resp = docs.get(f"/databases/{SHARED_NAME}/collections/characters/documents/aldric")
    assert resp.status_code == 403, "book grant leaked into the document server"


def test_document_grant_does_not_grant_book(app, docs_app, auth_store):
    """The converse: a docs database grant must not unlock a like-named book."""
    # An admin-created book that 'mara' has no chronos grant on.
    admin = app.test_client()
    assert _login(admin, "admin", "admin-pass").status_code == 200
    assert admin.post(f"/books/{SHARED_NAME}", json={"title": "x"}).status_code == 201

    auth_store.add_grant(
        WRITER, SHARED_NAME, None, None, ["read", "write", "delete"], granted_by="admin"
    )
    chronos = app.test_client()
    assert _login(chronos).status_code == 200
    assert chronos.get(f"/books/{SHARED_NAME}").status_code == 403


def test_collaborator_invite_leaves_document_grants_alone(app, docs_app, auth_store):
    """Re-inviting a collaborator must not delete their document-server grants."""
    auth_store.create_user("finn", generate_password_hash("pw"))
    auth_store.add_grant(
        "finn", SHARED_NAME, None, None, ["read"], granted_by="admin"
    )  # a document-server grant

    owner = app.test_client()
    assert _login(owner).status_code == 200
    owner.post(f"/books/{SHARED_NAME}", json={"title": "x"})
    for _ in range(2):  # invite twice -- idempotent
        assert owner.put(
            f"/books/{SHARED_NAME}/collaborators/finn", json={"role": "editor"}
        ).status_code == 200

    grants = auth_store.grants_for("finn")
    docs_grants = [g for g in grants if g["resource_type"] == "database"]
    book_grants = [g for g in grants if g["resource_type"] == BOOK_RESOURCE]
    assert len(docs_grants) == 1, "document-server grant was clobbered"
    assert len(book_grants) == 1, "invite should be idempotent"


# -- pure authz unit tests ---------------------------------------------------


def test_resource_type_must_match_exactly():
    book_grant = {"resource_type": "book", "database": "x", "perms": ["read"]}
    assert is_allowed([book_grant], "read", "x", resource_type="book")
    assert not is_allowed([book_grant], "read", "x")  # defaults to "database"


def test_legacy_grant_without_resource_type_is_a_database_grant():
    """Grants written before the field existed keep working for document-server."""
    legacy = {"database": "x", "collection": None, "doc_id": None, "perms": ["read"]}
    assert is_allowed([legacy], "read", "x")
    assert not is_allowed([legacy], "read", "x", resource_type="book")
