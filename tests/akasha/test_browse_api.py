"""HTTP-level tests for browse, suggest, version, diff and restore endpoints."""

import pytest
from conftest import login
from werkzeug.security import generate_password_hash


@pytest.fixture
def user_client(app, auth_store):
    """A non-admin client factory: create the user, grant, and log in.

    Returns a callable ``make(username, grants)`` where grants is a list of
    ``(database, collection, doc_id, perms)`` tuples.
    """
    def make(username="bob", grants=()):
        auth_store.create_user(username, generate_password_hash("pw"), role="user")
        for database, collection, doc_id, perms in grants:
            auth_store.add_grant(username, database, collection, doc_id, list(perms), granted_by="admin")
        c = app.test_client()
        assert login(c, username, "pw").status_code == 200
        return c
    return make


def _seed(client):
    client.post("/databases/earth/collections/lotr")
    client.post("/databases/earth/collections/lotr/documents/aragorn",
                json={"title": "Aragorn", "body": "Heir of [[isildur]]", "race": "Man"})
    client.post("/databases/earth/collections/lotr/documents/frodo",
                json={"title": "Frodo", "race": "Hobbit"})
    client.post("/databases/mars/collections/colony")
    client.post("/databases/mars/collections/colony/documents/dome",
                json={"title": "Dome One"})


# -- browse ---------------------------------------------------------------

def test_admin_lists_all_databases(client):
    _seed(client)
    dbs = client.get("/databases").get_json()["databases"]
    assert "earth" in dbs and "mars" in dbs
    assert "_auth" not in dbs


def test_user_only_sees_granted_databases(client, user_client):
    _seed(client)
    bob = user_client("bob", [("earth", "lotr", None, ["read"])])
    dbs = bob.get("/databases").get_json()["databases"]
    assert dbs == ["earth"]


def test_user_only_sees_granted_collections(client, user_client):
    _seed(client)
    client.post("/databases/earth/collections/hobbiton")
    bob = user_client("bob", [("earth", "lotr", None, ["read"])])
    cols = bob.get("/databases/earth/collections").get_json()["collections"]
    assert cols == ["lotr"]


def test_list_documents_filtered_to_readable(client, user_client):
    _seed(client)
    # Bob may read only the single article 'aragorn'.
    bob = user_client("bob", [("earth", "lotr", "aragorn", ["read"])])
    docs = bob.get("/databases/earth/collections/lotr/documents").get_json()["documents"]
    assert {d["id"] for d in docs} == {"aragorn"}
    assert docs[0]["title"] == "Aragorn"


def test_reserved_database_rejected(client):
    assert client.get("/databases/_auth/collections").status_code == 400


# -- suggest --------------------------------------------------------------

def test_suggest_matches_title_and_slug(client):
    _seed(client)
    sug = client.get("/suggest?q=arag").get_json()["suggestions"]
    assert any(s["slug"] == "aragorn" for s in sug)


def test_suggest_is_grant_filtered(client, user_client):
    _seed(client)
    bob = user_client("bob", [("earth", "lotr", "aragorn", ["read"])])
    slugs = {s["slug"] for s in bob.get("/suggest?q=o").get_json()["suggestions"]}
    assert "dome" not in slugs and "frodo" not in slugs


def test_suggest_empty_query_returns_nothing(client):
    assert client.get("/suggest?q=").get_json()["suggestions"] == []


# -- versions / diff / restore -------------------------------------------

def _doc(id="aragorn"):
    return f"/databases/earth/collections/lotr/documents/{id}"


def test_versions_listed_newest_first(client):
    _seed(client)
    client.put(_doc(), json={"title": "Elessar"}, headers={"If-Match": "1"})
    versions = client.get(_doc() + "/versions").get_json()["versions"]
    assert [v["rev"] for v in versions] == [2, 1]
    assert all("document" not in v for v in versions)


def test_get_single_version(client):
    _seed(client)
    snap = client.get(_doc() + "/versions/1").get_json()
    assert snap["rev"] == 1
    assert snap["document"]["title"] == "Aragorn"


def test_diff_endpoint(client):
    _seed(client)
    client.put(_doc(), json={"title": "Aragorn", "race": "Man", "weapon": "Anduril"},
               headers={"If-Match": "1"})
    diff = client.get(_doc() + "/diff?from=1&to=2").get_json()["diff"]
    statuses = {f["key"]: f["status"] for f in diff["fields"]}
    assert statuses["weapon"] == "added"
    assert statuses["body"] == "removed"


def test_diff_missing_revision_404(client):
    _seed(client)
    assert client.get(_doc() + "/diff?from=1&to=99").status_code == 404


def test_diff_bad_params_400(client):
    _seed(client)
    assert client.get(_doc() + "/diff?from=1").status_code == 400


def test_restore_creates_new_revision(client):
    _seed(client)
    client.put(_doc(), json={"title": "Elessar"}, headers={"If-Match": "1"})
    restored = client.post(_doc() + "/restore/1")
    assert restored.status_code == 200
    assert restored.get_json()["rev"] == 3
    assert client.get(_doc()).get_json()["document"]["title"] == "Aragorn"


def test_restore_after_delete_revives(client):
    _seed(client)
    rev = client.get(_doc()).get_json()["rev"]
    client.delete(_doc(), headers={"If-Match": str(rev)})
    assert client.get(_doc()).status_code == 404
    restored = client.post(_doc() + "/restore/1")
    assert restored.status_code == 200
    assert client.get(_doc()).get_json()["document"]["title"] == "Aragorn"


def test_cannot_restore_a_deletion(client):
    _seed(client)
    rev = client.get(_doc()).get_json()["rev"]
    client.delete(_doc(), headers={"If-Match": str(rev)})
    delete_rev = client.get(_doc() + "/versions").get_json()["versions"][0]["rev"]
    assert client.post(_doc() + f"/restore/{delete_rev}").status_code == 404


# -- OCC at the HTTP layer -----------------------------------------------

def test_update_with_stale_if_match_conflicts(client):
    _seed(client)
    client.put(_doc(), json={"title": "Elessar"}, headers={"If-Match": "1"})
    resp = client.put(_doc(), json={"title": "Strider"}, headers={"If-Match": "1"})
    assert resp.status_code == 409


def test_update_without_if_match_is_last_write_wins(client):
    _seed(client)
    resp = client.put(_doc(), json={"title": "Elessar"})
    assert resp.status_code == 200


def test_bad_if_match_value_400(client):
    _seed(client)
    assert client.put(_doc(), json={"x": 1}, headers={"If-Match": "abc"}).status_code == 400


# -- authz ---------------------------------------------------------------

def test_versions_require_read_permission(client, user_client):
    _seed(client)
    bob = user_client("bob", [("earth", "lotr", "frodo", ["read"])])
    assert bob.get(_doc("aragorn") + "/versions").status_code == 403
    assert bob.get(_doc("frodo") + "/versions").status_code == 200


def test_restore_requires_write_permission(client, user_client):
    _seed(client)
    bob = user_client("bob", [("earth", "lotr", "aragorn", ["read"])])
    assert bob.post(_doc("aragorn") + "/restore/1").status_code == 403


def test_browse_requires_authentication(anon_client):
    assert anon_client.get("/databases").status_code == 401
