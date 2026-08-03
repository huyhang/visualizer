"""Tests for the auth-hardening features:

- password strength policy (NIST 800-63B) and temp-password generation,
- invite-only registration mode,
- forced password change on first login (and self-service change),
- admins being subject to grants (no content bypass),
- per-IP rate limiting on the auth endpoints.
"""

import re

import mongomock
import pytest
from conftest import (
    ADMIN_PASS,
    ADMIN_USER,
    COLLECTION,
    DB,
    collection_url,
    doc_url,
    login,
    register,
)
from werkzeug.security import generate_password_hash

from visualizer.akasha.app import create_app
from visualizer.akasha.auth_store import (
    REGISTRATION_INVITE,
    REGISTRATION_OPEN,
    AuthStore,
    registration_allowed,
)
from visualizer.akasha.errors import WeakPassword
from visualizer.akasha.passwords import (
    MIN_PASSWORD_LENGTH,
    generate_temp_password,
    validate_password_strength,
)
from visualizer.akasha.store import DocumentStore

STRONG = "correct-horse-battery"
STRONG2 = "another-strong-secret"


# -- pure: password strength policy ------------------------------------------


def test_password_strength_accepts_a_strong_password():
    assert validate_password_strength(STRONG, "alice") == STRONG


def test_password_strength_rejects_too_short():
    with pytest.raises(WeakPassword):
        validate_password_strength("a" * (MIN_PASSWORD_LENGTH - 1), "alice")


def test_password_strength_rejects_too_long():
    with pytest.raises(WeakPassword):
        validate_password_strength("a" * 200, "alice")


def test_password_strength_rejects_common_password():
    with pytest.raises(WeakPassword):
        validate_password_strength("password123", "alice")


def test_password_strength_rejects_equal_to_username():
    with pytest.raises(WeakPassword):
        validate_password_strength("Aragorn-Ranger", "aragorn-ranger")


def test_password_strength_requires_a_string():
    with pytest.raises(WeakPassword):
        validate_password_strength(None)


# -- pure: temp-password generation ------------------------------------------


def test_generated_temp_password_passes_the_policy():
    for _ in range(50):
        pw = generate_temp_password()
        assert validate_password_strength(pw) == pw


def test_generated_temp_passwords_differ():
    assert generate_temp_password() != generate_temp_password()


# -- pure: registration policy -----------------------------------------------


def test_registration_allowed_open_always():
    assert registration_allowed(REGISTRATION_OPEN, 0) is True
    assert registration_allowed(REGISTRATION_OPEN, 5) is True


def test_registration_allowed_invite_only_after_bootstrap():
    # Invite mode still lets the very first account bootstrap the deployment...
    assert registration_allowed(REGISTRATION_INVITE, 0) is True
    # ...but blocks self-registration once any account exists.
    assert registration_allowed(REGISTRATION_INVITE, 1) is False


# -- auth store: settings + must_change_password -----------------------------


def test_registration_mode_defaults_to_open_and_persists():
    store = AuthStore(mongomock.MongoClient())
    assert store.get_registration_mode() == REGISTRATION_OPEN
    store.set_registration_mode(REGISTRATION_INVITE)
    assert store.get_registration_mode() == REGISTRATION_INVITE


def test_set_registration_mode_rejects_unknown():
    store = AuthStore(mongomock.MongoClient())
    with pytest.raises(ValueError):
        store.set_registration_mode("nonsense")


def test_create_user_records_must_change_flag():
    store = AuthStore(mongomock.MongoClient())
    store.create_user("a", "h", must_change_password=True)
    assert store.get_user("a")["must_change_password"] is True


def test_set_password_clears_flag_by_default_and_can_set_it():
    store = AuthStore(mongomock.MongoClient())
    store.create_user("a", "h", must_change_password=True)
    store.set_password("a", "h2")  # a voluntary/first-login change clears it
    assert store.get_user("a")["must_change_password"] is False
    store.set_password("a", "h3", must_change_password=True)  # an admin reset sets it
    assert store.get_user("a")["must_change_password"] is True


# -- helpers for HTTP tests --------------------------------------------------


def _build_app(seed_admin=True, admin_grant_all=False):
    """A fresh app + auth_store, with rate limiting left enabled by default."""
    client = mongomock.MongoClient()
    store = DocumentStore(client)
    store.create_collection(DB, COLLECTION)
    auth = AuthStore(client)
    if seed_admin:
        auth.create_user(ADMIN_USER, generate_password_hash(ADMIN_PASS), role="admin")
        if admin_grant_all:
            auth.grant_owner(ADMIN_USER, None, None, None, ["read", "write", "delete"])
    app = create_app(store, auth, secret_key="test-secret")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    return app, auth


# -- HTTP: invite-only registration ------------------------------------------


def test_invite_only_blocks_self_registration(app, auth_store):
    auth_store.set_registration_mode(REGISTRATION_INVITE)
    anon = app.test_client()
    resp = register(anon, "alice", STRONG)
    assert resp.status_code == 403
    assert auth_store.get_user("alice") is None


def test_invite_only_still_allows_bootstrapping_first_account():
    client = mongomock.MongoClient()
    store = DocumentStore(client)
    auth = AuthStore(client)
    auth.set_registration_mode(REGISTRATION_INVITE)
    app = create_app(store, auth, secret_key="test-secret")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)

    resp = register(app.test_client(), "founder", STRONG)
    assert resp.status_code == 201
    assert resp.get_json()["role"] == "admin"


def test_register_enforces_password_strength(anon_client):
    assert register(anon_client, "alice", "short").status_code == 400


def test_admin_can_toggle_registration_mode(client, auth_store):
    resp = client.post("/admin/settings/registration", data={"mode": "invite"})
    assert resp.status_code == 302
    assert auth_store.get_registration_mode() == REGISTRATION_INVITE
    client.post("/admin/settings/registration", data={"mode": "open"})
    assert auth_store.get_registration_mode() == REGISTRATION_OPEN


# -- HTTP: admin-created accounts + forced first-login change -----------------


def test_admin_create_user_auto_generates_temp_password(client, auth_store, app):
    # Blank password -> the server generates and displays a strong temporary one.
    resp = client.post("/admin/users", data={"username": "newbie", "role": "user"})
    assert resp.status_code == 200
    record = auth_store.get_user("newbie")
    assert record is not None
    assert record["must_change_password"] is True

    # The generated credential is shown once in the page; it must actually work.
    match = re.search(r'id="temp-cred">([^<]+)<', resp.get_data(as_text=True))
    assert match, "generated password not shown on the admin page"
    temp_password = match.group(1)
    assert login(app.test_client(), "newbie", temp_password).status_code == 200


def test_admin_reset_password_generates_and_shows_a_temp_password(client, auth_store, app):
    auth_store.create_user("resetme", generate_password_hash("old-strong-secret"))

    resp = client.post("/admin/users/resetme/reset-password")
    assert resp.status_code == 200
    # A generated credential is shown once...
    match = re.search(r'id="temp-cred">([^<]+)<', resp.get_data(as_text=True))
    assert match, "generated password not shown on the admin page"
    temp_password = match.group(1)

    # ...the old password no longer works, the generated one does...
    assert login(app.test_client(), "resetme", "old-strong-secret").status_code == 400
    assert login(app.test_client(), "resetme", temp_password).status_code == 200
    # ...and the user is forced to change it.
    assert auth_store.get_user("resetme")["must_change_password"] is True


def test_admin_created_user_must_change_password_before_using_the_app(auth_store, app):
    auth_store.create_user(
        "provisioned",
        generate_password_hash(STRONG),
        must_change_password=True,
    )
    c = app.test_client()

    # Login succeeds but flags the forced change.
    body = login(c, "provisioned", STRONG).get_json()
    assert body["must_change_password"] is True

    # ...and content is blocked until they change it.
    blocked = c.get(doc_url("anything"))
    assert blocked.status_code == 403

    # Set a new password; the forced-change flag clears.
    changed = c.post(
        "/change-password", json={"password": STRONG2, "confirm_password": STRONG2}
    )
    assert changed.status_code == 200
    assert auth_store.get_user("provisioned")["must_change_password"] is False

    # No longer blocked (auth/me is reachable again).
    assert c.get("/auth/me").status_code == 200


def test_change_password_rejects_mismatch_and_weak(auth_store, app):
    auth_store.create_user(
        "u", generate_password_hash(STRONG), must_change_password=True
    )
    c = app.test_client()
    login(c, "u", STRONG)
    assert (
        c.post(
            "/change-password",
            json={"password": STRONG2, "confirm_password": "different-secret"},
        ).status_code
        == 400
    )
    assert (
        c.post(
            "/change-password", json={"password": "short", "confirm_password": "short"}
        ).status_code
        == 400
    )


# -- HTTP: admins are subject to grants (no content bypass) -------------------


def test_admin_cannot_read_another_users_content_without_a_grant():
    app, auth = _build_app(seed_admin=True, admin_grant_all=False)
    auth.create_user("writer", generate_password_hash(STRONG))

    writer = app.test_client()
    login(writer, "writer", STRONG)
    assert writer.post(collection_url(database="db", collection="c")).status_code == 201
    assert writer.post(doc_url("secret", database="db", collection="c"), json={"n": 1}).status_code == 201

    admin = app.test_client()
    login(admin, ADMIN_USER, ADMIN_PASS)
    # The admin holds no grant on the writer's content.
    assert admin.get(doc_url("secret", database="db", collection="c")).status_code == 403
    # ...and cannot even see the database exists.
    assert admin.get("/databases").get_json()["databases"] == []


def test_admin_sees_content_only_where_explicitly_granted():
    app, auth = _build_app(seed_admin=True, admin_grant_all=False)
    auth.create_user("writer", generate_password_hash(STRONG))
    writer = app.test_client()
    login(writer, "writer", STRONG)
    writer.post(collection_url(database="db", collection="c"))
    writer.post(doc_url("secret", database="db", collection="c"), json={"n": 1})

    # Grant the admin read on that one article.
    auth.add_grant(ADMIN_USER, "db", "c", "secret", ["read"], granted_by=ADMIN_USER)

    admin = app.test_client()
    login(admin, ADMIN_USER, ADMIN_PASS)
    assert admin.get(doc_url("secret", database="db", collection="c")).status_code == 200


# -- HTTP: rate limiting -----------------------------------------------------


def test_login_is_rate_limited():
    # A fresh app with limiting *enabled* (5/minute on the auth endpoints).
    app, _ = _build_app()
    app.config.update(RATELIMIT_ENABLED=True)
    c = app.test_client()

    statuses = [login(c, "nobody", "wrong-password").status_code for _ in range(7)]
    assert 429 in statuses, f"expected a 429 among {statuses}"
