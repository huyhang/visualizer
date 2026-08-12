"""Grants must not leak between services sharing one `_auth` store.

Regression tests for the bug where a chronos book grant was written as a
akasha *database* grant: creating a book named "x" silently conferred
read/write/delete on a akasha database also named "x".
"""

import pytest
from werkzeug.security import generate_password_hash

from visualizer.akasha.app import create_app as create_docs_app
from visualizer.akasha.store import DocumentStore
from visualizer.auth.authz import is_allowed
from visualizer.chronos.app import BOOK_RESOURCE

# The collision case: a book and a akasha database with the SAME name.
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
    assert resp.status_code == 403, "book grant leaked into Akasha"


def test_book_grant_does_not_make_the_like_named_database_visible(app, docs_app):
    """Refusing the *articles* is not enough; the shelf must not appear either.

    The document check was always strict, so a leaked book grant produced a
    database that listed every collection and no articles at all — empty
    shelves, with names on them, belonging to someone else's world. Anyone a
    book was shared with saw it, because sharing a book is what hands out the
    grant that did it.
    """
    chronos = app.test_client()
    assert _login(chronos).status_code == 200
    assert chronos.post(f"/books/{SHARED_NAME}", json={"title": "x"}).status_code == 201

    docs = docs_app.test_client()
    assert _login(docs).status_code == 200
    assert docs.get("/databases").get_json()["databases"] == []
    listed = docs.get(f"/databases/{SHARED_NAME}/collections").get_json()
    assert (listed or {}).get("collections", []) == []


def test_a_calendar_grant_does_not_make_a_database_named_after_you_visible(
    app, docs_app, auth_store
):
    """The same leak through the newer door.

    A library calendar's grant puts its *owner's name* in the scope's database
    field, so a writer named after an Akasha database would otherwise hand it
    out with every calendar they shared.
    """
    auth_store.add_grant(
        WRITER, SHARED_NAME, None, "imperial", ["read"],
        granted_by="admin", resource_type="calendar",
    )
    docs = docs_app.test_client()
    assert _login(docs).status_code == 200
    assert docs.get("/databases").get_json()["databases"] == []


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
    """Re-inviting a collaborator must not delete their akasha grants."""
    auth_store.create_user("finn", generate_password_hash("pw"))
    auth_store.add_grant(
        "finn", SHARED_NAME, None, None, ["read"], granted_by="admin"
    )  # a akasha grant

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
    assert len(docs_grants) == 1, "akasha grant was clobbered"
    assert len(book_grants) == 1, "invite should be idempotent"


def test_deleting_a_book_leaves_the_like_named_document_grants_alone(
    app, docs_app, auth_store,
):
    """Deleting a book sweeps its grants; the sweep must stop at the namespace.

    ``mara`` holds an akasha grant on a database with the same name as the book
    she is deleting -- the exact collision this module exists for. Losing it
    would revoke her access to a world she never touched.
    """
    auth_store.add_grant(
        WRITER, SHARED_NAME, None, None, ["read"], granted_by="admin"
    )  # an akasha grant
    chronos = app.test_client()
    assert _login(chronos).status_code == 200
    assert chronos.post(f"/books/{SHARED_NAME}", json={"title": "x"}).status_code == 201
    assert chronos.delete(f"/books/{SHARED_NAME}").status_code == 204

    remaining = auth_store.grants_for(WRITER)
    assert [g["resource_type"] for g in remaining] == ["database"]
    docs = docs_app.test_client()
    assert _login(docs).status_code == 200
    assert docs.get(
        f"/databases/{SHARED_NAME}/collections/characters/documents/aldric"
    ).status_code == 200


# -- pure authz unit tests ---------------------------------------------------


def test_resource_type_must_match_exactly():
    book_grant = {"resource_type": "book", "database": "x", "perms": ["read"]}
    assert is_allowed([book_grant], "read", "x", resource_type="book")
    assert not is_allowed([book_grant], "read", "x")  # defaults to "database"


def test_legacy_grant_without_resource_type_is_a_database_grant():
    """Grants written before the field existed keep working for akasha."""
    legacy = {"database": "x", "collection": None, "doc_id": None, "perms": ["read"]}
    assert is_allowed([legacy], "read", "x")
    assert not is_allowed([legacy], "read", "x", resource_type="book")
