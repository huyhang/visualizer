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

def _names(entries):
    return [e["name"] for e in entries]


def test_admin_lists_all_databases(client):
    _seed(client)
    dbs = _names(client.get("/databases").get_json()["databases"])
    assert "earth" in dbs and "mars" in dbs
    assert "_auth" not in dbs


def test_user_only_sees_granted_databases(client, user_client):
    _seed(client)
    bob = user_client("bob", [("earth", "lotr", None, ["read"])])
    dbs = bob.get("/databases").get_json()["databases"]
    assert _names(dbs) == ["earth"]


def test_user_only_sees_granted_collections(client, user_client):
    _seed(client)
    client.post("/databases/earth/collections/hobbiton")
    bob = user_client("bob", [("earth", "lotr", None, ["read"])])
    cols = bob.get("/databases/earth/collections").get_json()["collections"]
    assert _names(cols) == ["lotr"]


def test_list_documents_filtered_to_readable(client, user_client):
    _seed(client)
    # Bob may read only the single article 'aragorn'.
    bob = user_client("bob", [("earth", "lotr", "aragorn", ["read"])])
    docs = bob.get("/databases/earth/collections/lotr/documents").get_json()["documents"]
    assert {d["id"] for d in docs} == {"aragorn"}
    assert docs[0]["title"] == "Aragorn"


def test_reserved_database_rejected(client):
    assert client.get("/databases/_auth/collections").status_code == 400


# -- browse: counts and permission hints ----------------------------------
# The cards and buttons a browse page draws come from these, so that the UI can
# say how much is inside and hide actions that would only earn a 403.

def test_database_summary_counts_what_you_can_see(client):
    _seed(client)
    earth = next(d for d in client.get("/databases").get_json()["databases"]
                 if d["name"] == "earth")
    assert earth == {"name": "earth", "title": "Earth", "collections": 1, "articles": 2}


def test_counts_exclude_articles_you_cannot_read(client, user_client):
    _seed(client)
    bob = user_client("bob", [("earth", "lotr", "aragorn", ["read"])])
    earth = bob.get("/databases").get_json()["databases"][0]
    assert earth["articles"] == 1  # not frodo
    lotr = bob.get("/databases/earth/collections").get_json()["collections"][0]
    assert lotr["articles"] == 1


def test_counts_exclude_deleted_articles(client):
    _seed(client)
    rev = client.get(_doc("frodo")).get_json()["rev"]
    client.delete(_doc("frodo"), headers={"If-Match": str(rev)})
    earth = client.get("/databases").get_json()["databases"][0]
    assert earth["articles"] == 1


def test_collection_reports_whether_you_may_add_to_it(client, user_client):
    _seed(client)
    bob = user_client("bob", [("earth", "lotr", None, ["read", "write"])])
    lotr = bob.get("/databases/earth/collections").get_json()["collections"][0]
    assert lotr["can_write"] is True
    assert lotr["can_delete"] is False  # write is not ownership


def test_write_on_one_article_is_not_permission_to_add_another(client, user_client):
    """A document-scoped grant must not light up the 'New article' button."""
    _seed(client)
    bob = user_client("bob", [("earth", "lotr", "aragorn", ["read", "write"])])
    lotr = bob.get("/databases/earth/collections").get_json()["collections"][0]
    assert lotr["can_write"] is False


# -- browse: filter, order and paging -------------------------------------

def test_documents_are_ordered_by_title(client):
    _seed(client)
    docs = client.get("/databases/earth/collections/lotr/documents").get_json()["documents"]
    assert [d["id"] for d in docs] == ["aragorn", "frodo"]


def test_filter_matches_body_text_not_just_the_title(client):
    """The filter box is the full-text search the API always had."""
    _seed(client)
    docs = client.get(
        "/databases/earth/collections/lotr/documents?filter=isildur"
    ).get_json()["documents"]
    assert [d["id"] for d in docs] == ["aragorn"]


def test_filter_requires_every_word(client):
    _seed(client)
    body = client.get(
        "/databases/earth/collections/lotr/documents?filter=aragorn hobbit"
    ).get_json()
    assert body["documents"] == []
    assert body["total"] == 0


def test_paging_reports_the_total_and_clamps_the_page(client):
    _seed(client)
    body = client.get(
        "/databases/earth/collections/lotr/documents?per_page=1&page=99"
    ).get_json()
    assert body["total"] == 2 and body["pages"] == 2
    assert body["page"] == 2  # clamped, not an error
    assert [d["id"] for d in body["documents"]] == ["frodo"]


def test_bad_paging_params_fall_back_rather_than_failing(client):
    _seed(client)
    body = client.get(
        "/databases/earth/collections/lotr/documents?page=nonsense"
    ).get_json()
    assert body["page"] == 1


def test_documents_carry_last_write_metadata(client):
    _seed(client)
    doc = client.get(
        "/databases/earth/collections/lotr/documents?filter=aragorn"
    ).get_json()["documents"][0]
    assert doc["author"] == "admin"
    assert doc["updated"]  # an ISO timestamp from the version history
    assert "fields" not in doc  # filter-only text is not shipped to the client


# -- recently edited -------------------------------------------------------

def test_recent_lists_newest_first_across_databases(client):
    _seed(client)
    client.put(_doc("frodo"), json={"title": "Frodo Baggins"}, headers={"If-Match": "1"})
    docs = client.get("/recent").get_json()["documents"]
    assert docs[0]["id"] == "frodo"
    assert {d["id"] for d in docs} == {"aragorn", "frodo", "dome"}


def test_recent_is_grant_filtered_and_limited(client, user_client):
    _seed(client)
    bob = user_client("bob", [("earth", "lotr", None, ["read"])])
    assert {d["id"] for d in bob.get("/recent").get_json()["documents"]} == {
        "aragorn", "frodo",
    }
    assert len(client.get("/recent?limit=1").get_json()["documents"]) == 1


# -- deleting a namespace --------------------------------------------------

def test_owner_deletes_an_empty_collection(client):
    _seed(client)
    client.post("/databases/earth/collections/spare")
    resp = client.delete("/databases/earth/collections/spare")
    assert resp.status_code == 200
    assert resp.get_json()["database_removed"] is False
    assert _names(
        client.get("/databases/earth/collections").get_json()["collections"]
    ) == ["lotr"]


def test_deleting_the_last_collection_removes_the_database(client):
    """Otherwise an abandoned 'new article' strands a database for ever."""
    client.post("/databases/limbo/collections/only")
    resp = client.delete("/databases/limbo/collections/only")
    # The caller is told, so it does not navigate to a page that just vanished.
    assert resp.get_json()["database_removed"] is True
    assert "limbo" not in _names(client.get("/databases").get_json()["databases"])


def test_collection_with_articles_is_not_deletable(client):
    _seed(client)
    assert client.delete("/databases/earth/collections/lotr").status_code == 409


def test_collection_with_only_a_tombstone_is_not_deletable(client):
    """A deleted article still has history, and nobody should lose it silently."""
    client.post("/databases/earth/collections/lotr")
    client.post(_doc("frodo"), json={"title": "Frodo"})
    client.delete(_doc("frodo"), headers={"If-Match": "1"})
    assert client.delete("/databases/earth/collections/lotr").status_code == 409


def test_purge_discards_the_history_and_reports_what_went(client):
    client.post("/databases/earth/collections/lotr")
    client.post(_doc("frodo"), json={"title": "Frodo"})
    client.delete(_doc("frodo"), headers={"If-Match": "1"})
    resp = client.delete("/databases/earth/collections/lotr?purge=1")
    assert resp.status_code == 200
    assert resp.get_json()["purged"] == 1
    assert "earth" not in _names(client.get("/databases").get_json()["databases"])


def test_purge_still_refuses_over_a_live_article(client):
    _seed(client)
    assert client.delete("/databases/earth/collections/lotr?purge=1").status_code == 409


def test_purge_flag_can_be_spelled_as_a_denial(client):
    client.post("/databases/earth/collections/lotr")
    client.post(_doc("frodo"), json={"title": "Frodo"})
    client.delete(_doc("frodo"), headers={"If-Match": "1"})
    assert client.delete("/databases/earth/collections/lotr?purge=false").status_code == 409


def test_the_owner_is_told_what_deleting_would_cost(client, user_client):
    """The list drives the confirm dialog's warning, so it carries the count."""
    _seed(client)
    rev = client.get(_doc("frodo")).get_json()["rev"]
    client.delete(_doc("frodo"), headers={"If-Match": str(rev)})
    listing = client.get("/databases/earth/collections/lotr/documents").get_json()
    assert listing["deleted"] == 1

    # Only the owner can act on it, so only the owner pays for the count.
    bob = user_client("bob", [("earth", "lotr", None, ["read"])])
    assert bob.get("/databases/earth/collections/lotr/documents").get_json()["deleted"] == 0


def test_non_owner_cannot_delete_a_collection(client, user_client):
    client.post("/databases/earth/collections/spare")
    bob = user_client("bob", [("earth", "spare", None, ["read", "write"])])
    assert bob.delete("/databases/earth/collections/spare").status_code == 403


def test_deleting_a_collection_revokes_its_grants(client, auth_store):
    client.post("/databases/earth/collections/spare")
    client.delete("/databases/earth/collections/spare")
    assert auth_store.grants_on("earth", "spare", None) == []


def test_seeing_no_collections_is_not_the_same_as_there_being_none(client, user_client):
    """Otherwise the world page would offer to delete a database full of other
    people's work — which the server would refuse anyway."""
    _seed(client)
    # Bob's grant names a collection that does not exist, so he can see the
    # database and nothing inside it.
    bob = user_client("bob", [("earth", "ghost", None, ["read"])])
    body = bob.get("/databases/earth/collections").get_json()
    assert body["collections"] == []
    assert body["empty"] is False

    client.post("/databases/void/collections/only")
    client.delete("/databases/void/collections/only")  # takes the database too
    assert client.get("/databases/earth/collections").get_json()["empty"] is False


def test_database_with_collections_is_not_deletable(client):
    _seed(client)
    assert client.delete("/databases/earth").status_code == 409


def test_reserved_database_cannot_be_deleted(client):
    assert client.delete("/databases/_auth").status_code == 400


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
