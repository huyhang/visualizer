"""The uniform sharing routes the account page drives, one kind at a time.

These are the HTTP half of ``visualizer.sharing``; the pure half is in
``test_sharing_kinds.py``. Every kind goes through the *same* registrar, so the
point of parameterising is that a fifth kind would be covered by adding one row
here rather than a new suite.

Two of the four kinds -- books and library calendars -- belong to Chronos, and
are exercised here against the **Akasha** app deliberately: sharing is pure grant
work on the store both services share, which is exactly what lets the account
page reach them without a cross-origin request.
"""

import pytest
from conftest import login, register

OWNER = ["read", "write", "delete"]

# (kind, grant scope as (database, collection, doc_id), resource_type, url tail)
KINDS = [
    ("collection", ("mine", "cast", None), "database", "mine/cast"),
    ("article", ("mine", "cast", "aldric"), "database", "mine/cast/aldric"),
    ("book", ("ember-pact", None, None), "book", "ember-pact"),
    ("calendar", ("alice", None, "imperial"), "calendar", "alice/imperial"),
]
IDS = [k[0] for k in KINDS]


def _user(app, username, password="correct-horse-battery"):
    register(app.test_client(), username, password)
    c = app.test_client()
    assert login(c, username, password).status_code == 200
    return c


@pytest.fixture
def alice(app, auth_store):
    """A writer, plus 'bo' to share with. Neither owns anything yet."""
    client = _user(app, "alice")
    _user(app, "bo")
    return client


def _own(auth_store, scope, resource_type, username="alice"):
    auth_store.grant_owner(username, *scope, OWNER, resource_type=resource_type)


def url(tail, kind):
    return f"/account/sharing/{kind}/{tail}/collaborators"


# -- the trio, for every kind -------------------------------------------------


@pytest.mark.parametrize("kind,scope,rtype,tail", KINDS, ids=IDS)
def test_an_owner_can_list_share_and_unshare(alice, auth_store, kind, scope, rtype, tail):
    _own(auth_store, scope, rtype)
    base = url(tail, kind)

    # Only the owner's own auto-grant to begin with.
    assert alice.get(base).get_json()["collaborators"] == [
        {"username": "alice", "role": "owner"}
    ]

    assert alice.put(f"{base}/bo", json={"role": "reader"}).status_code == 200
    people = alice.get(base).get_json()["collaborators"]
    assert {"username": "bo", "role": "reader"} in people

    # Idempotent: re-sharing replaces the role rather than stacking a second grant.
    assert alice.put(f"{base}/bo", json={"role": "editor"}).status_code == 200
    people = alice.get(base).get_json()["collaborators"]
    assert [p for p in people if p["username"] == "bo"] == [
        {"username": "bo", "role": "editor"}
    ]

    assert alice.delete(f"{base}/bo").status_code == 204
    assert all(p["username"] != "bo" for p in alice.get(base).get_json()["collaborators"])


@pytest.mark.parametrize("kind,scope,rtype,tail", KINDS, ids=IDS)
def test_a_non_owner_cannot_share_or_even_look(app, alice, auth_store, kind, scope, rtype, tail):
    """Reader access is not permission to pass access on."""
    _own(auth_store, scope, rtype)
    auth_store.add_grant("bo", *scope, ["read"], granted_by="alice", resource_type=rtype)
    bo = app.test_client()
    login(bo, "bo", "correct-horse-battery")

    base = url(tail, kind)
    assert bo.get(base).status_code == 403
    assert bo.put(f"{base}/alice", json={"role": "reader"}).status_code == 403
    assert bo.delete(f"{base}/alice").status_code == 403


@pytest.mark.parametrize("kind,scope,rtype,tail", KINDS, ids=IDS)
def test_sharing_with_an_unknown_user_is_refused(alice, auth_store, kind, scope, rtype, tail):
    _own(auth_store, scope, rtype)
    assert alice.put(f"{url(tail, kind)}/nobody", json={"role": "reader"}).status_code == 404


@pytest.mark.parametrize("kind,scope,rtype,tail", KINDS, ids=IDS)
def test_you_cannot_share_with_yourself(alice, auth_store, kind, scope, rtype, tail):
    """It could only *reduce* your own access, so it is refused rather than
    risking locking an owner out of their own work."""
    _own(auth_store, scope, rtype)
    assert alice.put(f"{url(tail, kind)}/alice", json={"role": "reader"}).status_code == 403


@pytest.mark.parametrize("kind,scope,rtype,tail", KINDS, ids=IDS)
def test_an_unknown_role_is_refused(alice, auth_store, kind, scope, rtype, tail):
    _own(auth_store, scope, rtype)
    assert alice.put(f"{url(tail, kind)}/bo", json={"role": "admin"}).status_code == 403


def test_sharing_requires_a_login(anon_client):
    resp = anon_client.get("/account/sharing/book/ember-pact/collaborators")
    assert resp.status_code in (302, 401)


# -- the kinds must not bleed into each other ---------------------------------


def test_owning_a_book_confers_nothing_on_a_same_named_world(alice, auth_store):
    """The bug this guards is real and was fixed once before in the listings:
    one grant store, three resource kinds, and a book id that looks exactly like
    a database name."""
    _own(auth_store, ("ember-pact", None, None), "book")
    # The book is shareable...
    assert alice.get("/account/sharing/book/ember-pact/collaborators").status_code == 200
    # ...but the same name as an Akasha collection is not owned at all.
    assert alice.get(
        "/account/sharing/collection/ember-pact/cast/collaborators"
    ).status_code == 403


def test_owning_a_calendar_confers_nothing_on_a_book_of_the_same_name(alice, auth_store):
    _own(auth_store, ("alice", None, "imperial"), "calendar")
    assert alice.get("/account/sharing/calendar/alice/imperial/collaborators").status_code == 200
    assert alice.get("/account/sharing/book/imperial/collaborators").status_code == 403


def test_sharing_a_book_does_not_disturb_the_same_users_article_access(alice, auth_store):
    """Re-sharing replaces the grant at *exactly* one scope, under one kind."""
    _own(auth_store, ("ember-pact", None, None), "book")
    _own(auth_store, ("mine", "cast", None), "database")
    auth_store.add_grant("bo", "mine", "cast", None, ["read", "write"],
                         granted_by="alice")

    alice.put("/account/sharing/book/ember-pact/collaborators/bo", json={"role": "reader"})
    alice.delete("/account/sharing/book/ember-pact/collaborators/bo")

    still = alice.get("/account/sharing/collection/mine/cast/collaborators").get_json()
    assert {"username": "bo", "role": "editor"} in still["collaborators"]


def test_reserved_namespaces_stay_unshareable(alice, auth_store):
    """The guard akasha's kinds carry and chronos's do not."""
    _own(auth_store, ("_auth", "users", None), "database")
    assert alice.get("/account/sharing/collection/_auth/users/collaborators").status_code == 400
