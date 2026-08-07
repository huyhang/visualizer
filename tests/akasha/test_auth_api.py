"""HTTP-level tests for authentication, authorization, and the admin flows."""

import mongomock
import pytest
from conftest import (
    ADMIN_USER,
    COLLECTION,
    DB,
    collection_url,
    doc_url,
    login,
    register,
    search_url,
)

from visualizer.akasha.app import create_app
from visualizer.akasha.config import get_secret_key, get_secure_cookies
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore


def test_create_app_requires_a_secret_key():
    client = mongomock.MongoClient()
    with pytest.raises(ValueError):
        create_app(DocumentStore(client), AuthStore(client), secret_key="")


def test_get_secret_key_requires_env(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        get_secret_key()
    monkeypatch.setenv("SECRET_KEY", "a-real-key")
    assert get_secret_key() == "a-real-key"


def test_get_secure_cookies_parses_env(monkeypatch):
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    assert get_secure_cookies() is False
    for truthy in ("true", "1", "YES", "On"):
        monkeypatch.setenv("SESSION_COOKIE_SECURE", truthy)
        assert get_secure_cookies() is True
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    assert get_secure_cookies() is False


def test_create_app_applies_secure_cookie_flag():
    client = mongomock.MongoClient()
    app = create_app(
        DocumentStore(client), AuthStore(client), secret_key="k", secure_cookies=True
    )
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True


# -- authentication gate ------------------------------------------------------


def test_document_api_requires_auth(anon_client):
    assert anon_client.get(doc_url("a1")).status_code == 401
    assert anon_client.post(collection_url(database="d", collection="c")).status_code == 401
    assert anon_client.get(search_url()).status_code == 401


def test_health_is_public(anon_client):
    assert anon_client.get("/health").status_code == 200


def test_register_then_login(anon_client):
    assert register(anon_client, "alice", "correct-horse-battery").status_code == 201
    assert login(anon_client, "alice", "correct-horse-battery").status_code == 200
    assert login(anon_client, "alice", "wrong").status_code == 400


def test_register_duplicate_conflicts(anon_client):
    register(anon_client, "alice", "correct-horse-battery")
    assert register(anon_client, "alice", "correct-horse-battery").status_code == 409


def test_register_requires_valid_email(anon_client):
    assert (
        anon_client.post(
            "/register", json={"username": "x", "password": "correct-horse-battery", "email": "nope"}
        ).status_code
        == 400
    )
    # Missing email entirely is also rejected.
    assert (
        anon_client.post(
            "/register", json={"username": "x", "password": "correct-horse-battery"}
        ).status_code
        == 400
    )


def test_register_returns_email_and_rejects_duplicate_email(anon_client):
    resp = register(anon_client, "alice", "correct-horse-battery", email="shared@example.com")
    assert resp.status_code == 201
    assert resp.get_json()["email"] == "shared@example.com"
    # A different username but the same email is a 409.
    assert register(anon_client, "bob", "correct-horse-battery", email="shared@example.com").status_code == 409


def test_first_registered_user_becomes_admin():
    """On a truly empty deployment the first account is the admin; the rest are users."""
    client = mongomock.MongoClient()
    app = create_app(
        DocumentStore(client), AuthStore(client), secret_key="test-secret"
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    c = app.test_client()

    first = register(c, "first", "correct-horse-battery")
    assert first.status_code == 201
    assert first.get_json()["role"] == "admin"

    second = register(c, "second", "correct-horse-battery")
    assert second.get_json()["role"] == "user"


def test_login_failures_are_indistinguishable(app, auth_store):
    """Unknown user, wrong password, and deactivated account must look identical."""
    # A deactivated account WITH the correct password is the sensitive case:
    # revealing it would leak both that the account exists and that the password
    # was right.
    auth_store.create_user("gone", _hash("rightpw"), email="gone@example.com")
    auth_store.update_user("gone", active=False)

    c = app.test_client()
    deactivated = login(c, "gone", "rightpw")
    wrong_pw = login(c, ADMIN_USER, "definitely-wrong")
    unknown = login(c, "no-such-user", "whatever")

    # Identical status code...
    assert {deactivated.status_code, wrong_pw.status_code, unknown.status_code} == {400}
    # ...and identical message: no enumeration signal.
    messages = {
        deactivated.get_json()["error"],
        wrong_pw.get_json()["error"],
        unknown.get_json()["error"],
    }
    assert messages == {"Invalid username or password."}


def test_reserved_database_is_blocked_even_for_admin(client):
    # Even an admin with an instance-wide grant must never reach the internal
    # auth database: the reserved-name guard runs before authorization.
    assert client.get("/databases/_auth/collections/users/documents/admin").status_code == 400


# -- authorization: a plain user with fine-grained grants ---------------------


def _new_user(anon_client, auth_store, username, password="correct-horse-battery"):
    """Register a user and return a client logged in as them."""
    register(anon_client, username, password)
    c = anon_client.application.test_client()
    login(c, username, password)
    return c


def test_user_with_no_grants_is_forbidden(app, auth_store):
    anon = app.test_client()
    user = _new_user(anon, auth_store, "alice")
    assert user.get(doc_url("a1")).status_code == 403


def test_fine_grained_grants_scope_access(app, auth_store, client):
    # Admin sets up two databases/collections with documents.
    client.post(collection_url(database="db1", collection="c1"))
    client.post(doc_url("x", database="db1", collection="c1"), json={"n": 1})
    client.post(collection_url(database="db2", collection="c2"))
    client.post(doc_url("x", database="db2", collection="c2"), json={"n": 2})
    client.post(doc_url("y", database="db2", collection="c2"), json={"n": 3})

    # Alice: full access to all of db1/c1, but only article "x" in db2/c2.
    auth_store.create_user("alice", _hash("correct-horse-battery"))
    auth_store.add_grant("alice", "db1", "c1", None, ["read", "write", "delete"], "admin")
    auth_store.add_grant("alice", "db2", "c2", "x", ["read"], "admin")

    alice = app.test_client()
    login(alice, "alice", "correct-horse-battery")

    # Full access in db1/c1 (including creating a new article).
    assert alice.get(doc_url("x", database="db1", collection="c1")).status_code == 200
    assert (
        alice.post(
            doc_url("new", database="db1", collection="c1"), json={"n": 9}
        ).status_code
        == 201
    )
    # Read the allow-listed article in db2/c2, but not write it or touch others.
    assert alice.get(doc_url("x", database="db2", collection="c2")).status_code == 200
    assert (
        alice.put(
            doc_url("x", database="db2", collection="c2"), json={"n": 5}
        ).status_code
        == 403
    )
    assert alice.get(doc_url("y", database="db2", collection="c2")).status_code == 403


def test_search_results_are_filtered_by_read_permission(app, auth_store, client):
    client.post(doc_url("aragorn"), json={"name": "Aragorn", "weapon": "sword"})
    client.post(doc_url("legolas"), json={"name": "Legolas", "weapon": "bow"})

    # Bob may read only "aragorn".
    auth_store.create_user("bob", _hash("correct-horse-battery"))
    auth_store.add_grant("bob", DB, COLLECTION, "aragorn", ["read"], "admin")

    bob = app.test_client()
    login(bob, "bob", "correct-horse-battery")
    body = bob.get(search_url(), query_string={"key": "weapon"}).get_json()
    assert body["count"] == 1
    assert {r["id"] for r in body["results"]} == {"aragorn"}


def test_creator_owns_new_document(app, auth_store, client):
    # Grant Carol write on the collection so she can create.
    auth_store.create_user("carol", _hash("correct-horse-battery"))
    auth_store.add_grant("carol", DB, COLLECTION, None, ["write"], "admin")

    carol = app.test_client()
    login(carol, "carol", "correct-horse-battery")
    assert carol.post(doc_url("mine"), json={"a": 1}).status_code == 201
    # Ownership auto-grant gives her full access to the article she created,
    # even though the collection grant was write-only.
    assert carol.get(doc_url("mine")).status_code == 200
    assert carol.delete(doc_url("mine")).status_code == 204


# -- admin flows --------------------------------------------------------------


def test_non_admin_cannot_reach_admin(app, auth_store):
    anon = app.test_client()
    user = _new_user(anon, auth_store, "alice")
    assert user.get("/admin").status_code == 403


def test_admin_can_grant_and_revoke_via_http(client, auth_store):
    auth_store.create_user("dave", _hash("correct-horse-battery"))
    # Add a grant through the admin endpoint.
    resp = client.post(
        "/admin/grants",
        data={
            "username": "dave",
            "database": "db",
            "collection": "col",
            "doc_id": "",
            "perms": ["read", "write"],
        },
    )
    assert resp.status_code == 302
    grants = auth_store.grants_for("dave")
    assert len(grants) == 1
    assert grants[0]["database"] == "db"
    assert grants[0]["collection"] == "col"
    assert grants[0]["doc_id"] is None
    assert set(grants[0]["perms"]) == {"read", "write"}

    # Revoke it.
    client.post(f"/admin/grants/{grants[0]['id']}/delete", data={"user": "dave"})
    assert auth_store.grants_for("dave") == []


def test_admin_can_create_user(client, auth_store, app):
    resp = client.post(
        "/admin/users",
        data={
            "username": "grace",
            "email": "grace@example.com",
            "password": "correct-horse-battery",
            "role": "user",
        },
    )
    assert resp.status_code == 302
    record = auth_store.get_user("grace")
    assert record is not None
    assert record["email"] == "grace@example.com"
    assert record["role"] == "user"
    # The admin-created account can log in.
    c = app.test_client()
    assert login(c, "grace", "correct-horse-battery").status_code == 200


def test_admin_create_user_rejects_bad_email(client, auth_store):
    resp = client.post(
        "/admin/users",
        data={"username": "bad", "email": "nope", "password": "correct-horse-battery"},
        follow_redirects=True,
    )
    assert resp.status_code == 200  # redirected back to /admin with a flashed error
    assert auth_store.get_user("bad") is None


def test_admin_can_create_another_admin(client, auth_store):
    client.post(
        "/admin/users",
        data={"username": "root2", "email": "root2@example.com", "password": "correct-horse-battery", "role": "admin"},
    )
    assert auth_store.get_user("root2")["role"] == "admin"


def test_admin_can_edit_email(client, auth_store):
    auth_store.create_user("heidi", _hash("correct-horse-battery"), email="old@example.com")
    resp = client.post("/admin/users/heidi/edit", data={"email": "new@example.com"})
    assert resp.status_code == 302
    assert auth_store.get_user("heidi")["email"] == "new@example.com"


def test_admin_can_reset_password(app, auth_store, client):
    auth_store.create_user("ivan", _hash("oldpw"), email="ivan@example.com")
    client.post("/admin/users/ivan/edit", data={"password": "reset-horse-battery"})
    c = app.test_client()
    assert login(c, "ivan", "oldpw").status_code == 400  # old password no longer works
    assert login(c, "ivan", "reset-horse-battery").status_code == 200  # new one does


def test_admin_edit_rejects_duplicate_email(client, auth_store):
    auth_store.create_user("judy", _hash("correct-horse-battery"), email="judy@example.com")
    auth_store.create_user("ken", _hash("correct-horse-battery"), email="ken@example.com")
    resp = client.post(
        "/admin/users/ken/edit",
        data={"email": "judy@example.com"},
        follow_redirects=True,
    )
    assert resp.status_code == 200  # redirected back with a flashed error
    assert auth_store.get_user("ken")["email"] == "ken@example.com"  # unchanged


def test_admin_can_toggle_role_and_active(client, auth_store):
    auth_store.create_user("erin", _hash("correct-horse-battery"))
    client.post("/admin/users/erin/role", data={"role": "admin"})
    assert auth_store.get_user("erin")["role"] == "admin"
    client.post("/admin/users/erin/active", data={"active": "false"})
    assert auth_store.get_user("erin")["active"] is False


def test_cannot_demote_or_delete_last_admin(client):
    # The seeded admin is the only admin.
    assert client.post(f"/admin/users/{ADMIN_USER}/role", data={"role": "user"}).status_code == 403
    assert client.post(f"/admin/users/{ADMIN_USER}/delete").status_code == 403


def test_deactivated_user_is_locked_out(app, auth_store, client):
    auth_store.create_user("frank", _hash("correct-horse-battery"))
    auth_store.add_grant("frank", DB, COLLECTION, None, ["read"], "admin")
    frank = app.test_client()
    login(frank, "frank", "correct-horse-battery")
    assert frank.get(doc_url("aragorn")).status_code in (200, 404)  # authorized (doc may not exist)

    # Admin deactivates Frank; his next request is unauthenticated.
    auth_store.update_user("frank", active=False)
    assert frank.get(doc_url("aragorn")).status_code == 401


def _hash(password):
    from werkzeug.security import generate_password_hash

    return generate_password_hash(password)
