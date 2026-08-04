"""HTTP-level tests for owner-driven sharing (collaborators) in akasha.

A resource's owner -- the creator, or anyone made an owner -- can grant other
users reader/editor/owner access to a collection or a single document, without
needing an admin. Mirrors the collaborator model chronos uses for books.
"""

from conftest import collection_url, doc_url, login
from werkzeug.security import generate_password_hash


def _hash(password):
    return generate_password_hash(password)


def _owned_collection(client):
    """The seeded admin owns everything via its instance-wide grant, but we want a
    concrete creator-owned collection. Create one as the given client."""
    assert client.post(collection_url(database="mine", collection="cast")).status_code == 201
    return "mine", "cast"


COLLAB = "/databases/mine/collections/cast/collaborators"


# -- collection sharing -------------------------------------------------------


def test_owner_can_share_and_revoke_a_collection(app, auth_store, client):
    _owned_collection(client)
    # The owner creates the article, so the owner (not the invitee) owns it.
    client.post(doc_url("aldric", database="mine", collection="cast"), json={"name": "Aldric"})
    auth_store.create_user("bob", _hash("correct-horse-battery"))

    # Share as editor.
    resp = client.put(f"{COLLAB}/bob", json={"role": "editor"})
    assert resp.status_code == 200
    assert resp.get_json()["role"] == "editor"

    # Bob can now read and write existing content in the collection...
    bob = app.test_client()
    login(bob, "bob", "correct-horse-battery")
    assert bob.get(doc_url("aldric", database="mine", collection="cast")).status_code == 200
    assert bob.put(
        doc_url("aldric", database="mine", collection="cast"), json={"name": "Aldric II"}
    ).status_code == 200
    # ...but not delete it (editor, not owner).
    assert bob.delete(
        doc_url("aldric", database="mine", collection="cast")
    ).status_code == 403

    # Revoke.
    assert client.delete(f"{COLLAB}/bob").status_code == 204
    bob2 = app.test_client()
    login(bob2, "bob", "correct-horse-battery")
    assert bob2.get(doc_url("aldric", database="mine", collection="cast")).status_code == 403


def test_reshare_replaces_the_role_and_is_idempotent(app, auth_store, client):
    _owned_collection(client)
    auth_store.create_user("bob", _hash("pw"))

    client.put(f"{COLLAB}/bob", json={"role": "editor"})
    client.put(f"{COLLAB}/bob", json={"role": "reader"})  # downgrade

    grants = [g for g in auth_store.grants_for("bob") if g["database"] == "mine"]
    assert len(grants) == 1, "re-sharing should replace, not stack, the grant"
    assert set(grants[0]["perms"]) == {"read"}


def test_owner_can_list_collaborators(app, auth_store, client):
    _owned_collection(client)
    auth_store.create_user("bob", _hash("pw"))
    auth_store.create_user("amy", _hash("pw"))
    client.put(f"{COLLAB}/bob", json={"role": "reader"})
    client.put(f"{COLLAB}/amy", json={"role": "owner"})

    body = client.get(COLLAB).get_json()
    people = {c["username"]: c["role"] for c in body["collaborators"]}
    # The owner themselves shows up too, alongside the invitees.
    assert people["bob"] == "reader"
    assert people["amy"] == "owner"


def test_a_new_owner_can_reshare(app, auth_store, client):
    """Granting the 'owner' role really confers ownership: they can share too."""
    _owned_collection(client)
    auth_store.create_user("amy", _hash("correct-horse-battery"))
    auth_store.create_user("bob", _hash("correct-horse-battery"))
    client.put(f"{COLLAB}/amy", json={"role": "owner"})

    amy = app.test_client()
    login(amy, "amy", "correct-horse-battery")
    assert amy.put(f"{COLLAB}/bob", json={"role": "reader"}).status_code == 200


# -- authorization ------------------------------------------------------------


def test_non_owner_cannot_share(app, auth_store, client):
    _owned_collection(client)
    # Eve is only a reader; she must not be able to invite anyone.
    auth_store.create_user("eve", _hash("correct-horse-battery"))
    auth_store.create_user("mallory", _hash("pw"))
    client.put(f"{COLLAB}/eve", json={"role": "reader"})

    eve = app.test_client()
    login(eve, "eve", "correct-horse-battery")
    assert eve.put(f"{COLLAB}/mallory", json={"role": "editor"}).status_code == 403
    assert eve.get(COLLAB).status_code == 403


def test_sharing_with_unknown_user_is_404(app, client):
    _owned_collection(client)
    assert client.put(f"{COLLAB}/ghost", json={"role": "reader"}).status_code == 404


def test_unknown_role_is_rejected(app, auth_store, client):
    _owned_collection(client)
    auth_store.create_user("bob", _hash("pw"))
    assert client.put(f"{COLLAB}/bob", json={"role": "superuser"}).status_code == 403


def test_cannot_share_a_resource_with_yourself(app, auth_store, client):
    _owned_collection(client)
    # 'client' is the admin; sharing with self is refused (would only reduce access).
    from conftest import ADMIN_USER

    assert client.put(f"{COLLAB}/{ADMIN_USER}", json={"role": "reader"}).status_code == 403


def test_sharing_requires_authentication(anon_client):
    assert anon_client.put(f"{COLLAB}/bob", json={"role": "reader"}).status_code == 401


def test_reserved_database_cannot_be_shared(client, auth_store):
    auth_store.create_user("bob", _hash("pw"))
    resp = client.put(
        "/databases/_auth/collections/users/collaborators/bob", json={"role": "reader"}
    )
    assert resp.status_code == 400


# -- document sharing ---------------------------------------------------------


def test_owner_can_share_a_single_document(app, auth_store, client):
    client.post(collection_url(database="mine", collection="cast"))
    client.post(doc_url("aldric", database="mine", collection="cast"), json={"name": "Aldric"})
    auth_store.create_user("bob", _hash("correct-horse-battery"))

    doc_collab = "/databases/mine/collections/cast/documents/aldric/collaborators"
    assert client.put(f"{doc_collab}/bob", json={"role": "reader"}).status_code == 200

    bob = app.test_client()
    login(bob, "bob", "correct-horse-battery")
    # Bob can read the one shared article...
    assert bob.get(doc_url("aldric", database="mine", collection="cast")).status_code == 200
    # ...but nothing else in the collection.
    client.post(doc_url("mara", database="mine", collection="cast"), json={"name": "Mara"})
    assert bob.get(doc_url("mara", database="mine", collection="cast")).status_code == 403


def test_ownership_grant_is_namespaced_and_does_not_touch_books(app, auth_store, client):
    """Sharing an akasha collection must not disturb a user's chronos grants."""
    _owned_collection(client)
    auth_store.create_user("bob", _hash("pw"))
    # A pre-existing chronos (book) grant on the same-named resource.
    auth_store.add_grant("bob", "mine", None, None, ["read"], granted_by="x", resource_type="book")

    client.put(f"{COLLAB}/bob", json={"role": "editor"})
    client.delete(f"{COLLAB}/bob")

    remaining = auth_store.grants_for("bob")
    assert any(g["resource_type"] == "book" for g in remaining), "book grant was clobbered"
