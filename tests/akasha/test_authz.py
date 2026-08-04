"""Unit tests for the pure access-control resolution (no DB, no Flask)."""

from visualizer.auth.authz import (
    DELETE,
    READ,
    WRITE,
    effective_perms,
    is_allowed,
    owned_resources,
    perm_for_method,
    resources_shared_with,
    role_for_perms,
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


# -- roles --------------------------------------------------------------------


def test_role_for_perms_names_known_bundles():
    assert role_for_perms([READ]) == "reader"
    assert role_for_perms([READ, WRITE]) == "editor"
    assert role_for_perms([WRITE, READ]) == "editor"  # order-independent
    assert role_for_perms([READ, WRITE, DELETE]) == "owner"


def test_role_for_perms_is_custom_when_no_bundle_matches():
    assert role_for_perms([WRITE]) == "custom"
    assert role_for_perms([]) == "custom"
    assert role_for_perms([READ, DELETE]) == "custom"


# -- owned resources ----------------------------------------------------------


def test_owned_resources_lists_only_delete_scoped_collections_and_documents():
    grants = [
        grant(database="db", collection="c", perms=[READ, WRITE, DELETE]),  # owned collection
        grant(database="db", collection="c", doc_id="a1", perms=[READ, WRITE, DELETE]),  # owned doc
        grant(database="db", collection="c2", perms=[READ, WRITE]),  # editor only, not owned
    ]
    assert owned_resources(grants) == [
        {"database": "db", "collection": "c", "doc_id": None},
        {"database": "db", "collection": "c", "doc_id": "a1"},
    ]


def test_owned_resources_excludes_database_and_instance_wide_grants():
    grants = [
        grant(perms=[READ, WRITE, DELETE]),  # instance-wide (admin) -- not a shareable unit
        grant(database="db", perms=[READ, WRITE, DELETE]),  # whole-database -- excluded
    ]
    assert owned_resources(grants) == []


def test_owned_resources_ignores_non_akasha_grants():
    book = {
        "resource_type": "book",
        "database": "b",
        "collection": "c",
        "doc_id": None,
        "perms": [READ, WRITE, DELETE],
    }
    assert owned_resources([book]) == []


def test_owned_resources_deduplicates_scopes():
    grants = [
        grant(database="db", collection="c", perms=[READ, WRITE, DELETE]),
        grant(database="db", collection="c", perms=[READ, WRITE, DELETE]),
    ]
    assert owned_resources(grants) == [
        {"database": "db", "collection": "c", "doc_id": None}
    ]


# -- resources shared with me -------------------------------------------------


def test_resources_shared_with_keeps_only_others_grants():
    grants = [
        # My own ownership auto-grant (granted_by me) -- not "shared with me".
        {**grant(database="db", collection="c", perms=[READ, WRITE, DELETE]), "granted_by": "me"},
        # Something Alice shared with me.
        {**grant(database="db", collection="c2", perms=[READ]), "granted_by": "alice"},
    ]
    assert resources_shared_with(grants, "me") == [
        {"database": "db", "collection": "c2", "doc_id": None, "role": "reader", "granted_by": "alice"}
    ]


def test_resources_shared_with_ignores_non_akasha_grants():
    book = {
        "resource_type": "book",
        "database": "b",
        "collection": None,
        "doc_id": None,
        "perms": [READ],
        "granted_by": "alice",
    }
    assert resources_shared_with([book], "me") == []
