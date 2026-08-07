"""Unit tests for DocumentStore against an in-memory MongoDB."""

import pytest

from visualizer.akasha.errors import (
    CollectionAlreadyExists,
    CollectionNotEmpty,
    CollectionNotFound,
    DatabaseNotEmpty,
    DatabaseNotFound,
    DocumentAlreadyExists,
    DocumentNotFound,
)

# Matches the default namespace pre-created by the `store` fixture (conftest).
DB = "testdb"
COL = "things"


def test_create_and_get_roundtrip(store):
    store.create(DB, COL, "a1", {"name": "Aragorn", "race": "Man"})
    assert store.get(DB, COL, "a1") == {
        "id": "a1",
        "document": {"name": "Aragorn", "race": "Man"},
        "rev": 1,
    }


def test_create_duplicate_raises(store):
    store.create(DB, COL, "a1", {"name": "Aragorn"})
    with pytest.raises(DocumentAlreadyExists):
        store.create(DB, COL, "a1", {"name": "Strider"})


def test_create_overrides_embedded_id(store):
    store.create(DB, COL, "real", {"_id": "fake", "name": "Frodo"})
    fetched = store.get(DB, COL, "real")
    assert fetched["id"] == "real"
    assert "_id" not in fetched["document"]


def test_get_missing_raises(store):
    with pytest.raises(DocumentNotFound):
        store.get(DB, COL, "nope")


def test_update_replaces_document(store):
    store.create(DB, COL, "a1", {"name": "Aragorn", "age": 87})
    store.update(DB, COL, "a1", {"name": "Elessar"})
    assert store.get(DB, COL, "a1")["document"] == {"name": "Elessar"}


def test_update_missing_raises(store):
    with pytest.raises(DocumentNotFound):
        store.update(DB, COL, "ghost", {"name": "x"})


def test_delete_removes_document(store):
    store.create(DB, COL, "a1", {"name": "Aragorn"})
    store.delete(DB, COL, "a1")
    with pytest.raises(DocumentNotFound):
        store.get(DB, COL, "a1")


def test_delete_missing_raises(store):
    with pytest.raises(DocumentNotFound):
        store.delete(DB, COL, "ghost")


def test_databases_and_collections_are_isolated(store):
    store.create_collection("db1", "c1")
    store.create("db1", "c1", "a1", {"where": "db1/c1"})
    with pytest.raises(DocumentNotFound):
        store.get("db2", "c1", "a1")
    with pytest.raises(DocumentNotFound):
        store.get("db1", "c2", "a1")


def test_create_collection_makes_namespace_usable(store):
    store.create_collection("newdb", "newcol")
    # Now documents can be created there.
    store.create("newdb", "newcol", "x", {"ok": True})
    assert store.get("newdb", "newcol", "x")["document"] == {"ok": True}


def test_create_collection_duplicate_raises(store):
    store.create_collection("newdb", "newcol")
    with pytest.raises(CollectionAlreadyExists):
        store.create_collection("newdb", "newcol")


def test_delete_collection_removes_an_empty_namespace(store):
    store.create_collection("newdb", "keep")
    store.create_collection("newdb", "drop")
    store.delete_collection("newdb", "drop")
    assert store.list_collections("newdb") == ["keep"]


def test_deleting_the_last_collection_drops_the_database(store):
    store.create_collection("newdb", "only")
    store.delete_collection("newdb", "only")
    assert "newdb" not in store.list_databases()


def test_delete_collection_refuses_while_documents_remain(store):
    store.create_collection("newdb", "full")
    store.create("newdb", "full", "x", {"a": 1})
    with pytest.raises(CollectionNotEmpty):
        store.delete_collection("newdb", "full")


def test_delete_collection_refuses_over_a_tombstone(store):
    """A soft-deleted document still carries history worth keeping."""
    store.create_collection("newdb", "full")
    store.create("newdb", "full", "x", {"a": 1})
    store.delete("newdb", "full", "x", expected_rev=1)
    with pytest.raises(CollectionNotEmpty):
        store.delete_collection("newdb", "full")


def test_purging_discards_tombstones_and_says_how_many(store):
    """The only way a collection that has ever held something can go."""
    store.create_collection("newdb", "full")
    store.create("newdb", "full", "x", {"a": 1})
    store.create("newdb", "full", "y", {"a": 2})
    store.delete("newdb", "full", "x", expected_rev=1)
    store.delete("newdb", "full", "y", expected_rev=1)
    assert store.count_deleted("newdb", "full") == 2
    assert store.delete_collection("newdb", "full", purge_history=True) == {
        "purged": 2, "database_removed": True,
    }


def test_purging_still_refuses_over_a_live_article(store):
    """Purging discards *history*; emptying a collection is a separate act."""
    store.create_collection("newdb", "full")
    store.create("newdb", "full", "x", {"a": 1})
    with pytest.raises(CollectionNotEmpty):
        store.delete_collection("newdb", "full", purge_history=True)


def test_delete_collection_reports_whether_the_database_survived(store):
    store.create_collection("newdb", "keep")
    store.create_collection("newdb", "drop")
    assert store.delete_collection("newdb", "drop") == {
        "purged": 0, "database_removed": False,
    }


def test_delete_collection_requires_it_to_exist(store):
    with pytest.raises(CollectionNotFound):
        store.delete_collection(DB, "ghostcol")


def test_delete_database_refuses_while_collections_remain(store):
    with pytest.raises(DatabaseNotEmpty):
        store.delete_database(DB)


def test_delete_database_requires_it_to_exist(store):
    with pytest.raises(DatabaseNotFound):
        store.delete_database("ghostdb")


def test_create_document_requires_existing_database(store):
    with pytest.raises(DatabaseNotFound):
        store.create("ghostdb", "ghostcol", "x", {"a": 1})


def test_create_document_requires_existing_collection(store):
    # DB exists (created by fixture) but the collection does not.
    with pytest.raises(CollectionNotFound):
        store.create(DB, "ghostcol", "x", {"a": 1})


def _seed_fellowship(store):
    store.create(DB, COL, "aragorn", {"name": "Aragorn", "weapon": "sword"})
    store.create(DB, COL, "legolas", {"name": "Legolas", "weapon": "bow"})
    store.create(DB, COL, "gimli", {"name": "Gimli", "axe": "battle axe"})


def test_search_by_key_returns_only_docs_with_key(store):
    _seed_fellowship(store)
    ids = {r["id"] for r in store.search(DB, COL, key="weapon")}
    assert ids == {"aragorn", "legolas"}


def test_search_by_key_is_top_level_only(store):
    store.create(DB, COL, "nested", {"stats": {"weapon": "hidden"}})
    store.create(DB, COL, "top", {"weapon": "visible"})
    ids = {r["id"] for r in store.search(DB, COL, key="weapon")}
    assert ids == {"top"}


def test_search_by_text_is_case_insensitive_substring(store):
    _seed_fellowship(store)
    ids = {r["id"] for r in store.search(DB, COL, text="BOW")}
    assert ids == {"legolas"}


def test_search_by_key_and_text_requires_both(store):
    _seed_fellowship(store)
    # 'weapon' key AND text 'sword' -> only Aragorn
    results = store.search(DB, COL, key="weapon", text="sword")
    assert [r["id"] for r in results] == ["aragorn"]
    # 'axe' key exists but text 'sword' does not -> empty
    assert store.search(DB, COL, key="axe", text="sword") == []


def test_search_text_ignores_injected_id(store):
    store.create(DB, COL, "frodo", {"name": "Baggins"})
    # 'frodo' only appears as the id, not in content -> no match
    assert store.search(DB, COL, text="frodo") == []
