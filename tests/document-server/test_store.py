"""Unit tests for DocumentStore against an in-memory MongoDB."""

import pytest

from errors import (
    CollectionAlreadyExists,
    CollectionNotFound,
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
