"""Unit tests for the pure access-control resolution (no DB, no Flask)."""

from visualizer.akasha.authz import (
    DELETE,
    READ,
    WRITE,
    effective_perms,
    is_allowed,
    perm_for_method,
)


def grant(database=None, collection=None, doc_id=None, perms=()):
    return {"database": database, "collection": collection, "doc_id": doc_id, "perms": list(perms)}


def test_perm_for_method_maps_http_verbs():
    assert perm_for_method("GET") == READ
    assert perm_for_method("post") == WRITE
    assert perm_for_method("PUT") == WRITE
    assert perm_for_method("DELETE") == DELETE


def test_no_grants_means_no_access():
    assert effective_perms([], "db", "col", "doc") == set()
    assert not is_allowed([], READ, "db", "col", "doc")


def test_database_wildcard_covers_everything_below():
    grants = [grant(database="db", perms=[READ, WRITE])]
    assert is_allowed(grants, READ, "db", "col", "doc")
    assert is_allowed(grants, WRITE, "db", "other", "x")
    assert not is_allowed(grants, DELETE, "db", "col", "doc")


def test_collection_grant_does_not_leak_to_other_collection():
    grants = [grant(database="db", collection="c1", perms=[READ, WRITE, DELETE])]
    assert is_allowed(grants, WRITE, "db", "c1", "anything")
    assert not is_allowed(grants, READ, "db", "c2", "anything")


def test_document_grant_is_isolated():
    grants = [grant(database="db", collection="c", doc_id="a1", perms=[READ])]
    assert is_allowed(grants, READ, "db", "c", "a1")
    assert not is_allowed(grants, READ, "db", "c", "a2")


def test_most_specific_grant_overrides_broader_one():
    # Broad read/write on the collection, but the article is narrowed to read-only.
    grants = [
        grant(database="db", collection="c", perms=[READ, WRITE, DELETE]),
        grant(database="db", collection="c", doc_id="a1", perms=[READ]),
    ]
    # On a1 the document-level grant wins: read only.
    assert effective_perms(grants, "db", "c", "a1") == {READ}
    assert not is_allowed(grants, WRITE, "db", "c", "a1")
    # Other articles still fall under the collection-level grant.
    assert is_allowed(grants, WRITE, "db", "c", "a2")


def test_same_specificity_grants_union_their_perms():
    grants = [
        grant(database="db", collection="c", doc_id="a1", perms=[READ]),
        grant(database="db", collection="c", doc_id="a1", perms=[WRITE]),
    ]
    assert effective_perms(grants, "db", "c", "a1") == {READ, WRITE}


def test_full_on_one_collection_but_specific_articles_on_another():
    """The exact scenario the design promised: broad here, allow-listed there."""
    grants = [
        grant(database="db1", collection="c1", perms=[READ, WRITE, DELETE]),
        grant(database="db2", collection="c2", doc_id="x", perms=[READ, WRITE]),
        grant(database="db2", collection="c2", doc_id="y", perms=[READ]),
    ]
    # Full access across all of db1/c1.
    assert is_allowed(grants, DELETE, "db1", "c1", "whatever")
    # Only the allow-listed articles in db2/c2.
    assert is_allowed(grants, WRITE, "db2", "c2", "x")
    assert is_allowed(grants, READ, "db2", "c2", "y")
    assert not is_allowed(grants, WRITE, "db2", "c2", "y")
    assert not is_allowed(grants, READ, "db2", "c2", "z")
