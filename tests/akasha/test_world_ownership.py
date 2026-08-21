"""Who owns a world, and what that lets them do.

A world used to be the one scope nobody could hold: grants were handed out for
collections and articles, so a whole database had an owner only if an
administrator typed one into the grants form. That made ``world`` unshareable in
principle -- sharing needs an owner -- and left Prithvi asking for a permission
the product had no way to issue.

Creating a world's first collection now claims the world as well, on the same
rule Akasha already applies one level down: you own what you make.
"""

from conftest import login, register

OWNER = {"read", "write", "delete"}


def _writer(app, username, password="correct-horse-battery"):
    register(app.test_client(), username, password)
    client = app.test_client()
    assert login(client, username, password).status_code == 200
    return client


def _world_grants(auth_store, username, database):
    return [
        grant
        for grant in auth_store.grants_for(username)
        if grant["database"] == database
        and grant["collection"] is None
        and grant["doc_id"] is None
        and (grant.get("resource_type") or "database") == "database"
    ]


def test_making_a_world_makes_you_its_owner(app, auth_store):
    alice = _writer(app, "alice")

    assert alice.post("/databases/hollow/collections/cast").status_code == 201

    [grant] = _world_grants(auth_store, "alice", "hollow")
    assert OWNER <= set(grant["perms"])


def test_a_second_category_does_not_hand_the_world_to_whoever_added_it(app, auth_store):
    """You own what you make. Adding to someone else's world is not making it."""
    alice = _writer(app, "alice")
    bo = _writer(app, "bo")
    alice.post("/databases/hollow/collections/cast")

    # bo can only add a category where alice's world grant lets him write.
    assert alice.put(
        "/account/sharing/world/hollow/collaborators/bo", json={"role": "editor"}
    ).status_code == 200
    assert bo.post("/databases/hollow/collections/places").status_code == 201

    assert _world_grants(auth_store, "bo", "hollow")[0]["perms"] == ["read", "write"]
    assert _world_grants(auth_store, "alice", "hollow"), "the maker still owns it"


def test_owning_the_world_is_what_lets_you_share_it(app):
    alice = _writer(app, "alice")
    _writer(app, "bo")
    alice.post("/databases/hollow/collections/cast")

    shared = alice.put(
        "/account/sharing/world/hollow/collaborators/bo", json={"role": "reader"}
    )
    people = alice.get("/account/sharing/world/hollow/collaborators").get_json()

    assert shared.status_code == 200
    assert {"username": "bo", "role": "reader"} in people["collaborators"]


def test_someone_elses_world_is_not_yours_to_share(app):
    alice = _writer(app, "alice")
    bo = _writer(app, "bo")
    alice.post("/databases/hollow/collections/cast")

    assert bo.put(
        "/account/sharing/world/hollow/collaborators/alice", json={"role": "reader"}
    ).status_code == 403


def test_a_world_shows_up_among_the_things_you_own(app):
    """The account page groups by kind, so a world gets its own tab and count."""
    alice = _writer(app, "alice")
    alice.post("/databases/hollow/collections/cast")

    page = alice.get("/account").get_data(as_text=True)

    assert 'data-mode="world"' in page
    assert "Worlds (1)" in page


def test_a_reserved_namespace_is_refused_before_anything_is_claimed(app, auth_store):
    alice = _writer(app, "alice")

    assert alice.post("/databases/_auth/collections/cast").status_code == 400
    assert _world_grants(auth_store, "alice", "_auth") == []


def test_the_world_grant_reaches_the_articles_inside_it(app, auth_store):
    """The point of the whole scope: one grant covers the canon beneath it."""
    alice = _writer(app, "alice")
    bo = _writer(app, "bo")
    alice.post("/databases/hollow/collections/cast")
    alice.post(
        "/databases/hollow/collections/cast/documents/aldric", json={"title": "Aldric"}
    )
    assert bo.get("/databases/hollow/collections/cast/documents/aldric").status_code == 403

    alice.put("/account/sharing/world/hollow/collaborators/bo", json={"role": "reader"})

    assert bo.get("/databases/hollow/collections/cast/documents/aldric").status_code == 200
