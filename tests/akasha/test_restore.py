"""Finding and recovering a deleted article.

Deletes are soft, so an article can always come back -- but nothing listed the
tombstones, which meant recovery required already knowing the slug you were
trying to recover. These cover the two ways back: by name (the article's own URL
still answers for its history) and by browsing (the category lists what was
deleted from it).
"""

import pytest
from conftest import login
from werkzeug.security import generate_password_hash

from visualizer.akasha.history import last_live_snapshot

COL = "/databases/earth/collections/lotr"
DOC = COL + "/documents/frodo"


@pytest.fixture
def user_client(app, auth_store):
    def make(username="bob", grants=()):
        auth_store.create_user(username, generate_password_hash("pw"), role="user")
        for database, collection, doc_id, perms in grants:
            auth_store.add_grant(username, database, collection, doc_id, list(perms),
                                 granted_by="admin")
        c = app.test_client()
        assert login(c, username, "pw").status_code == 200
        return c
    return make


@pytest.fixture
def deleted(client):
    """A collection holding one live article and one deleted one."""
    client.post(COL)
    client.post(COL + "/documents/aragorn", json={"title": "Aragorn"})
    client.post(DOC, json={"title": "Frodo", "race": "Hobbit"})
    client.delete(DOC, headers={"If-Match": "1"})
    return client


# -- pure: which version a restore would bring back --------------------------


def test_the_newest_snapshot_with_a_body_is_the_one_to_restore():
    history = [
        {"rev": 1, "document": {"title": "A"}},
        {"rev": 2, "document": {"title": "B"}},
        {"rev": 3, "document": None},  # the delete
    ]
    assert last_live_snapshot(history)["rev"] == 2


def test_nothing_to_restore_when_history_holds_only_deletions():
    """Pruning really can leave a document unrecoverable, and the UI has to be
    able to say so rather than offer a button that cannot work."""
    assert last_live_snapshot([{"rev": 9, "document": None}]) is None
    assert last_live_snapshot([]) is None


# -- by name: the article's own URL ------------------------------------------


def test_a_deleted_article_still_answers_for_its_history(deleted):
    """This is what makes the "Restore" offer on its own page possible."""
    assert deleted.get(DOC).status_code == 404
    versions = deleted.get(DOC + "/versions").get_json()["versions"]
    assert [(v["rev"], v["op"]) for v in versions] == [(2, "delete"), (1, "create")]


def test_restoring_brings_the_body_back(deleted):
    assert deleted.post(DOC + "/restore/1").status_code == 200
    body = deleted.get(DOC).get_json()
    assert body["document"] == {"title": "Frodo", "race": "Hobbit"}
    assert body["rev"] == 3  # a new revision, not a rewind


# -- by browsing: the category's deleted list --------------------------------


def test_the_category_lists_what_was_deleted_from_it(deleted):
    rows = deleted.get(COL + "/deleted").get_json()["documents"]
    assert [r["id"] for r in rows] == ["frodo"]
    row = rows[0]
    # The tombstone has no body, so the title comes from the last version that
    # had one -- what the article was called when it went.
    assert row["title"] == "Frodo"
    assert row["restore_rev"] == 1
    assert row["deleted_by"] == "admin"
    assert row["deleted_at"]
    assert row["can_restore"] is True


def test_live_articles_are_not_in_the_deleted_list(deleted):
    rows = deleted.get(COL + "/deleted").get_json()["documents"]
    assert "aragorn" not in [r["id"] for r in rows]


def test_the_list_empties_once_everything_is_restored(deleted):
    deleted.post(DOC + "/restore/1")
    assert deleted.get(COL + "/deleted").get_json()["documents"] == []


def test_the_count_on_the_listing_tells_the_page_to_offer_the_drawer(deleted):
    """The category page only draws the section when there is something in it."""
    assert deleted.get(COL + "/documents").get_json()["deleted"] == 1
    deleted.post(DOC + "/restore/1")
    assert deleted.get(COL + "/documents").get_json()["deleted"] == 0


def test_an_editor_sees_the_count_not_just_an_owner(deleted, user_client):
    """It drives recovery, not only the delete-collection warning."""
    bob = user_client("bob", [("earth", "lotr", None, ["read", "write"])])
    assert bob.get(COL + "/documents").get_json()["deleted"] == 1


# -- who may see and undo what -----------------------------------------------


def test_the_deleted_list_is_grant_filtered(deleted, user_client):
    bob = user_client("bob", [("earth", "lotr", "aragorn", ["read"])])
    assert bob.get(COL + "/deleted").get_json()["documents"] == []


def test_a_reader_is_told_it_is_not_theirs_to_restore(deleted, user_client):
    """Rather than being shown a button that would 403."""
    bob = user_client("bob", [("earth", "lotr", None, ["read"])])
    [row] = bob.get(COL + "/deleted").get_json()["documents"]
    assert row["can_restore"] is False
    assert row["restore_rev"] == 1  # there *is* a version; bob just may not apply it
    assert bob.post(DOC + "/restore/1").status_code == 403


def test_the_deleted_list_needs_authentication(anon_client):
    assert anon_client.get(COL + "/deleted").status_code == 401


def test_reserved_databases_stay_unreachable(client):
    assert client.get("/databases/_auth/collections/users/deleted").status_code == 400


# -- the purge closes the door -----------------------------------------------


def test_purging_the_category_removes_what_could_have_been_restored(client):
    """The one irreversible act: after it, there is nothing left to list."""
    client.post(COL)
    client.post(DOC, json={"title": "Frodo"})
    client.delete(DOC, headers={"If-Match": "1"})
    assert client.get(COL + "/deleted").get_json()["documents"]

    client.delete(COL + "?purge=1")
    assert client.post(DOC + "/restore/1").status_code == 404
