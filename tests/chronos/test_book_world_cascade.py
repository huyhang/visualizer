"""Inviting someone to a book also lets them read its world.

A timeline is references. Handed a book and nothing else, a collaborator sees
that a scene happens at ``locations/highkeep`` and cannot open Highkeep, which
is not a useful thing to have been given. So the invite carries a **reader**
grant on the book's ``world`` -- and only a reader, and only when the person
doing the sharing is entitled to hand that world out at all.

This is not the old bug wearing a new coat. That one was a book grant being
*mistaken* for a world grant, one row doing two jobs; ``test_grant_isolation``
still holds that line. This writes a second, separate, visible grant on purpose.
"""

import pytest
from werkzeug.security import generate_password_hash

from visualizer.auth.authz import is_allowed

from .conftest import WRITER

BOOK = "ember-pact"
WORLD = "ember-pact"
OWNER = ["read", "write", "delete"]


@pytest.fixture
def devi(app, auth_store):
    """Somebody to share with, holding nothing at all to begin with."""
    auth_store.create_user("devi", generate_password_hash("devi-pw"))
    client = app.test_client()
    assert client.post(
        "/login", json={"username": "devi", "password": "devi-pw"}
    ).status_code == 200
    return client


def make_book(client, world=WORLD):
    body = {"title": "The Ember Pact"}
    if world is not None:
        body["world"] = world
    return client.post(f"/books/{BOOK}", json=body)


def own_the_world(auth_store, username=WRITER, world=WORLD):
    auth_store.grant_owner(username, world, None, None, OWNER)


def reads(auth_store, username, world=WORLD):
    return is_allowed(auth_store.grants_for(username), "read", world)


def writes(auth_store, username, world=WORLD):
    return is_allowed(auth_store.grants_for(username), "write", world)


def test_sharing_a_book_hands_over_its_world_as_a_reader(client, auth_store, devi):
    own_the_world(auth_store)
    make_book(client)

    shared = client.put(f"/books/{BOOK}/collaborators/devi", json={"role": "editor"})

    assert shared.status_code == 200
    assert shared.get_json()["world"] == WORLD
    assert reads(auth_store, "devi")
    assert not writes(auth_store, "devi"), "a book invite must not hand over the canon"


def test_a_book_with_no_world_has_nothing_to_cascade_to(client, auth_store, devi):
    own_the_world(auth_store)
    make_book(client, world=None)

    shared = client.put(f"/books/{BOOK}/collaborators/devi", json={"role": "editor"})

    assert shared.get_json()["world"] is None
    assert not reads(auth_store, "devi")


def test_you_cannot_pass_on_a_world_you_do_not_own(client, auth_store, devi):
    """Owning a book confers nothing over the canon it points at.

    The book is still shared -- the cascade declines rather than failing the
    whole invite, because the book was the thing actually being given.
    """
    make_book(client)  # ...but nobody granted WRITER the world

    shared = client.put(f"/books/{BOOK}/collaborators/devi", json={"role": "editor"})

    assert shared.status_code == 200
    assert shared.get_json()["world"] is None
    assert not reads(auth_store, "devi")
    assert client.get(f"/books/{BOOK}/collaborators").status_code == 200


def test_the_cascade_never_demotes_someone_who_already_has_more(
    client, auth_store, devi
):
    """``share`` replaces the grant at a scope, so an unguarded cascade would
    quietly turn an editor of the world into a reader of it."""
    own_the_world(auth_store)
    auth_store.add_grant("devi", WORLD, None, None, ["read", "write"], granted_by=WRITER)
    make_book(client)

    client.put(f"/books/{BOOK}/collaborators/devi", json={"role": "editor"})

    assert writes(auth_store, "devi"), "the cascade downgraded an existing editor"


def test_re_inviting_does_not_pile_up_world_grants(client, auth_store, devi):
    own_the_world(auth_store)
    make_book(client)

    for role in ("reader", "editor", "reader"):
        client.put(f"/books/{BOOK}/collaborators/devi", json={"role": role})

    world_grants = [
        g for g in auth_store.grants_for("devi")
        if g["database"] == WORLD and g["collection"] is None and g["doc_id"] is None
        and (g.get("resource_type") or "database") == "database"
    ]
    assert len(world_grants) == 1


def test_unsharing_the_book_leaves_the_world_alone(client, auth_store, devi):
    """Deliberate asymmetry: the cascade adds, and never takes away.

    Revoking it here would be a way to strip access somebody may have been given
    separately, and the world is now shareable in its own right -- so taking it
    back is one explicit action away.
    """
    own_the_world(auth_store)
    make_book(client)
    client.put(f"/books/{BOOK}/collaborators/devi", json={"role": "editor"})

    assert client.delete(f"/books/{BOOK}/collaborators/devi").status_code == 204

    assert not is_allowed(
        auth_store.grants_for("devi"), "read", BOOK, resource_type="book"
    )
    assert reads(auth_store, "devi"), "the world grant is separate and stays"


def test_the_two_grants_stay_distinguishable(client, auth_store, devi):
    """One invite, two rows, each in its own namespace -- not one row doing two jobs."""
    own_the_world(auth_store)
    make_book(client)
    client.put(f"/books/{BOOK}/collaborators/devi", json={"role": "editor"})

    kinds = sorted(
        (g.get("resource_type") or "database", tuple(g["perms"]))
        for g in auth_store.grants_for("devi")
        if g["database"] == BOOK
    )
    assert kinds == [("book", ("read", "write")), ("database", ("read",))]


# -- both spellings of the same invite ----------------------------------------


@pytest.fixture
def account_page(mongo_client, story_store, auth_store, doc_store):
    """Akasha's app, wired the way the entrypoints wire it.

    The account page shares books too, over its own uniform routes. It reaches
    Chronos data through one injected function and nothing else -- which is the
    whole reason the cascade hangs off the *kind* rather than off a route.
    """
    from visualizer.akasha.app import create_app

    app = create_app(
        doc_store,
        auth_store,
        secret_key="test-secret",
        book_world=lambda book: (story_store.get_book(book) or {}).get("world"),
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    client = app.test_client()
    assert client.post(
        "/login", json={"username": WRITER, "password": "mara-pass"}
    ).status_code == 200
    return client


def test_the_account_page_shares_the_world_exactly_as_chronos_does(
    client, account_page, auth_store, devi
):
    """The bug this guards: one route cascaded and the other quietly did not,
    so whether your collaborator could read the canon depended on which page
    you happened to invite them from."""
    own_the_world(auth_store)
    make_book(client)

    shared = account_page.put(
        "/account/sharing/book/ember-pact/collaborators/devi", json={"role": "editor"}
    )

    assert shared.status_code == 200
    assert shared.get_json()["also"]["database"] == WORLD
    assert reads(auth_store, "devi")
    assert not writes(auth_store, "devi")


def test_an_akasha_app_with_no_resolver_shares_the_book_alone(
    client, auth_store, devi, doc_store
):
    """Standalone with nothing injected, it degrades to book-only rather than
    failing -- but both shipped entrypoints do inject it."""
    from visualizer.akasha.app import create_app

    app = create_app(doc_store, auth_store, secret_key="test-secret")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    page = app.test_client()
    page.post("/login", json={"username": WRITER, "password": "mara-pass"})
    own_the_world(auth_store)
    make_book(client)

    shared = page.put(
        "/account/sharing/book/ember-pact/collaborators/devi", json={"role": "editor"}
    )

    assert shared.status_code == 200
    assert shared.get_json().get("also") is None
    assert not reads(auth_store, "devi")
