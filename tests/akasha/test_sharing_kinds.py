"""The pure half of ``visualizer.sharing``: kinds, and the two account lists.

No store, no Flask -- grants are plain dictionaries, which is the whole point of
describing a shareable kind by the *shape* of its grant. The route half is
covered by ``test_account_sharing_api.py``.
"""

import pytest

from visualizer.sharing import (
    ARTICLE,
    BOOK,
    CALENDAR,
    COLLECTION,
    WORLD,
    ResourceKind,
    account_sharing_url,
    owned_resources,
    resources_shared_with,
)

KINDS = [WORLD, COLLECTION, ARTICLE, BOOK, CALENDAR]

OWNER = ["read", "write", "delete"]
EDITOR = ["read", "write"]
READER = ["read"]


def grant(perms=OWNER, *, resource_type="database", database=None, collection=None,
          doc_id=None, granted_by="me", username="me"):
    return {
        "username": username, "resource_type": resource_type, "database": database,
        "collection": collection, "doc_id": doc_id, "perms": list(perms),
        "granted_by": granted_by,
    }


# -- telling the kinds apart --------------------------------------------------


@pytest.mark.parametrize("kind,g", [
    (WORLD, grant(database="mid")),
    (COLLECTION, grant(database="mid", collection="chars")),
    (ARTICLE, grant(database="mid", collection="chars", doc_id="aragorn")),
    (BOOK, grant(resource_type="book", database="ember-pact")),
    (CALENDAR, grant(resource_type="calendar", database="mara", doc_id="imperial")),
], ids=["world", "collection", "article", "book", "calendar"])
def test_each_kind_matches_only_its_own_grant_shape(kind, g):
    assert kind.matches(g)
    assert [k.name for k in KINDS if k.matches(g)] == [kind.name], (
        "exactly one kind must claim a grant, or the account page lists it twice"
    )


def test_only_the_instance_wide_wildcard_matches_no_kind():
    """A whole database is a *world* now, and a world is a shareable thing.

    What is left over is the wildcard an administrator holds, which names no
    resource at all: access-management territory rather than something with an
    owner who could pass it on.
    """
    assert [k.name for k in KINDS if k.matches(grant(database="mid"))] == ["world"]
    assert not any(k.matches(grant()) for k in KINDS)


def test_resource_type_is_never_a_wildcard():
    """The bug this guards: a book named 'x' unlocking a world named 'x'."""
    book_grant = grant(resource_type="book", database="ember-pact")
    assert not COLLECTION.matches(book_grant) and not ARTICLE.matches(book_grant)
    # ...and the reverse, which is why BOOK checks the type rather than arity:
    # a bare database grant has a book's *shape* and is a world, not a book.
    assert not BOOK.matches(grant(database="ember-pact"))
    assert WORLD.matches(grant(database="ember-pact"))


def test_a_legacy_grant_with_no_resource_type_is_akashas():
    legacy = {"username": "me", "database": "mid", "collection": "chars",
              "doc_id": None, "perms": OWNER}
    assert COLLECTION.matches(legacy)


def test_describe_names_the_resource_not_its_context():
    assert ARTICLE.describe({"database": "mid", "collection": "chars",
                             "doc_id": "aragorn"}) == "aragorn"
    assert COLLECTION.describe({"database": "mid", "collection": "chars",
                                "doc_id": None}) == "chars"
    assert CALENDAR.describe({"database": "mara", "collection": None,
                              "doc_id": "imperial"}) == "imperial"


# -- what the account page lists ----------------------------------------------


def test_owned_resources_spans_every_kind():
    grants = [
        grant(database="mid"),
        grant(database="mid", collection="chars"),
        grant(database="mid", collection="chars", doc_id="aragorn"),
        grant(resource_type="book", database="ember-pact"),
        grant(resource_type="calendar", database="mara", doc_id="imperial"),
    ]
    assert [(r["kind"], r["database"]) for r in owned_resources(grants, KINDS)] == [
        ("article", "mid"), ("book", "ember-pact"),
        ("calendar", "mara"), ("collection", "mid"), ("world", "mid"),
    ]


def test_owned_resources_needs_delete():
    """Ownership is holding delete; an editor cannot pass access on."""
    grants = [grant(EDITOR, resource_type="book", database="ember-pact")]
    assert owned_resources(grants, KINDS) == []


def test_owned_resources_collapses_duplicate_scopes():
    twice = [grant(resource_type="book", database="ember-pact")] * 2
    assert len(owned_resources(twice, KINDS)) == 1


def test_shared_with_me_excludes_what_i_granted_and_what_i_own():
    grants = [
        grant(READER, resource_type="book", database="theirs", granted_by="bo"),
        grant(EDITOR, database="mid", collection="chars", granted_by="me"),
        grant(OWNER, resource_type="book", database="mine", granted_by="bo"),
    ]
    shared = resources_shared_with(grants, "me", KINDS)
    assert [(r["kind"], r["database"], r["role"], r["granted_by"]) for r in shared] == [
        ("book", "theirs", "reader", "bo")
    ]


def test_a_world_shared_with_me_is_named_but_still_not_mine_to_pass_on():
    """It used to arrive nameless, because a world was not a kind of thing.

    Now it is named, and the two lists still separate correctly: reading a
    world is being told about it, owning one is being able to share it.
    """
    grants = [grant(READER, database="mid", granted_by="bo")]
    [row] = resources_shared_with(grants, "me", KINDS)
    assert (row["kind"], row["database"], row["role"]) == ("world", "mid", "reader")
    assert owned_resources(grants, KINDS) == []


def test_the_instance_wide_grant_is_still_shared_with_me_under_no_kind():
    """What an administrator holds: real access, naming no resource."""
    [row] = resources_shared_with([grant(READER, granted_by="bo")], "me", KINDS)
    assert row["kind"] is None and row["database"] is None


# -- the url the page appends a username to -----------------------------------


@pytest.mark.parametrize("kind,scope,expected", [
    (WORLD, {"database": "mid"}, "/account/sharing/world/mid/collaborators"),
    (COLLECTION, {"database": "mid", "collection": "chars"},
     "/account/sharing/collection/mid/chars/collaborators"),
    (ARTICLE, {"database": "mid", "collection": "chars", "doc_id": "aragorn"},
     "/account/sharing/article/mid/chars/aragorn/collaborators"),
    (BOOK, {"database": "ember-pact"},
     "/account/sharing/book/ember-pact/collaborators"),
    (CALENDAR, {"database": "mara", "doc_id": "imperial"},
     "/account/sharing/calendar/mara/imperial/collaborators"),
], ids=["world", "collection", "article", "book", "calendar"])
def test_account_sharing_url_covers_each_scope_shape(kind, scope, expected):
    assert account_sharing_url(kind, scope) == expected


def test_blanks_is_the_complement_of_fills():
    """The meta-check: a kind added later cannot forget to say what it leaves
    null, because it is derived rather than declared."""
    kind = ResourceKind(name="k", label="K", plural="Ks", fills=("database",))
    assert kind.blanks == ("collection", "doc_id")
