"""Unit tests for AuthStore against an in-memory MongoDB."""

import mongomock
import pytest

from visualizer.akasha.auth_store import AuthStore
from visualizer.akasha.errors import UserAlreadyExists, UserNotFound


@pytest.fixture
def auth():
    return AuthStore(mongomock.MongoClient())


def test_create_and_get_user(auth):
    auth.create_user("alice", "hash", role="user")
    record = auth.get_user("alice")
    assert record["username"] == "alice"
    assert record["role"] == "user"
    assert record["active"] is True
    assert record["password_hash"] == "hash"


def test_get_missing_user_returns_none(auth):
    assert auth.get_user("nobody") is None


def test_duplicate_user_raises(auth):
    auth.create_user("alice", "hash")
    with pytest.raises(UserAlreadyExists):
        auth.create_user("alice", "other")


def test_list_users_excludes_password_hash(auth):
    auth.create_user("alice", "hash", email="alice@example.com")
    users = auth.list_users()
    assert users == [
        {"username": "alice", "email": "alice@example.com", "role": "user", "active": True}
    ]


def test_email_must_be_unique(auth):
    from visualizer.akasha.errors import EmailAlreadyExists

    auth.create_user("alice", "h", email="dup@example.com")
    with pytest.raises(EmailAlreadyExists):
        auth.create_user("bob", "h", email="dup@example.com")


def test_update_user_role_and_active(auth):
    auth.create_user("alice", "hash")
    auth.update_user("alice", role="admin", active=False)
    record = auth.get_user("alice")
    assert record["role"] == "admin"
    assert record["active"] is False


def test_update_missing_user_raises(auth):
    with pytest.raises(UserNotFound):
        auth.update_user("ghost", role="admin")


def test_update_user_email(auth):
    auth.create_user("alice", "hash", email="old@example.com")
    auth.update_user("alice", email="new@example.com")
    assert auth.get_user("alice")["email"] == "new@example.com"


def test_update_user_email_rejects_clash_with_other_user(auth):
    from visualizer.akasha.errors import EmailAlreadyExists

    auth.create_user("alice", "h", email="alice@example.com")
    auth.create_user("bob", "h", email="bob@example.com")
    with pytest.raises(EmailAlreadyExists):
        auth.update_user("bob", email="alice@example.com")


def test_update_user_can_keep_own_email(auth):
    # Re-setting a user's email to its current value is not a clash.
    auth.create_user("alice", "h", email="alice@example.com")
    auth.update_user("alice", email="alice@example.com", active=False)
    assert auth.get_user("alice")["active"] is False


def test_set_password(auth):
    auth.create_user("alice", "old-hash")
    auth.set_password("alice", "new-hash")
    assert auth.get_user("alice")["password_hash"] == "new-hash"


def test_set_password_missing_user_raises(auth):
    with pytest.raises(UserNotFound):
        auth.set_password("ghost", "h")


def test_delete_user_also_removes_their_grants(auth):
    auth.create_user("alice", "hash")
    auth.add_grant("alice", "db", None, None, ["read"], granted_by="admin")
    auth.delete_user("alice")
    assert auth.get_user("alice") is None
    assert auth.grants_for("alice") == []


def test_count_admins(auth):
    auth.create_user("a", "h", role="admin")
    auth.create_user("b", "h", role="user")
    auth.create_user("c", "h", role="admin")
    assert auth.count_admins() == 2


def test_add_and_read_grant_public_shape(auth):
    auth.create_user("alice", "hash")
    g = auth.add_grant("alice", "db", "col", "doc", ["read", "write"], granted_by="admin")
    assert g["database"] == "db"
    assert g["collection"] == "col"
    assert g["doc_id"] == "doc"
    assert g["perms"] == ["read", "write"]
    assert g["granted_by"] == "admin"
    assert isinstance(g["id"], str) and g["id"]
    assert auth.grants_for("alice") == [g]


def test_delete_grant(auth):
    auth.create_user("alice", "hash")
    g = auth.add_grant("alice", "db", None, None, ["read"], granted_by="admin")
    auth.delete_grant(g["id"])
    assert auth.grants_for("alice") == []


def test_delete_grant_tolerates_bad_id(auth):
    # Should not raise on a non-ObjectId string.
    auth.delete_grant("not-an-object-id")


def test_grant_owner_is_idempotent_and_merges_perms(auth):
    auth.create_user("alice", "hash")
    auth.grant_owner("alice", "db", "col", "doc", ["read"])
    auth.grant_owner("alice", "db", "col", "doc", ["read", "write"])
    grants = auth.grants_for("alice")
    assert len(grants) == 1
    assert set(grants[0]["perms"]) == {"read", "write"}
