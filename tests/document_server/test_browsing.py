"""Unit tests for the pure browse/suggest helpers."""

from visualizer.document_server.browsing import (
    rank_suggestions,
    visible_collections,
    visible_databases,
)


def grant(database=None, collection=None, doc_id=None, perms=("read",)):
    return {"database": database, "collection": collection, "doc_id": doc_id, "perms": list(perms)}


def test_wildcard_grant_sees_all_databases():
    grants = [grant()]  # database=None -> any
    assert visible_databases(grants, ["a", "b"]) == ["a", "b"]


def test_database_grant_scopes_visibility():
    grants = [grant(database="earth")]
    assert visible_databases(grants, ["earth", "mars"]) == ["earth"]


def test_doc_level_grant_makes_its_database_visible():
    grants = [grant(database="earth", collection="lotr", doc_id="aragorn")]
    assert visible_databases(grants, ["earth", "mars"]) == ["earth"]


def test_write_only_grant_does_not_grant_read_visibility():
    grants = [grant(database="earth", perms=("write",))]
    assert visible_databases(grants, ["earth"]) == []


def test_visible_collections_scopes_by_database_and_collection():
    grants = [grant(database="earth", collection="lotr")]
    assert visible_collections(grants, "earth", ["lotr", "hobbit"]) == ["lotr"]
    assert visible_collections(grants, "mars", ["lotr"]) == []


def test_collection_wildcard_in_database():
    grants = [grant(database="earth")]  # whole database
    assert visible_collections(grants, "earth", ["lotr", "hobbit"]) == ["lotr", "hobbit"]


def test_rank_suggestions_nearest_scope_first():
    items = [
        {"slug": "far", "title": "Far", "database": "other", "collection": "x"},
        {"slug": "same-col", "title": "SameCol", "database": "earth", "collection": "lotr"},
        {"slug": "same-db", "title": "SameDb", "database": "earth", "collection": "hobbit"},
    ]
    ranked = rank_suggestions(items, current_db="earth", current_col="lotr")
    assert [r["slug"] for r in ranked] == ["same-col", "same-db", "far"]


def test_rank_suggestions_ties_break_on_title():
    items = [
        {"slug": "b", "title": "Beta", "database": "d", "collection": "c"},
        {"slug": "a", "title": "Alpha", "database": "d", "collection": "c"},
    ]
    ranked = rank_suggestions(items)
    assert [r["title"] for r in ranked] == ["Alpha", "Beta"]
