"""Persistence layer for user accounts and access-control grants.

``AuthStore`` is to authentication what ``DocumentStore`` is to documents: the
single seam between the app and MongoDB. It receives its Mongo client via the
constructor (inversion of control) so tests inject an in-memory client and
production injects a real one -- the same pattern, and often the *same* client,
as ``DocumentStore``.

Everything it owns lives in a dedicated, reserved database (``_auth``) that is
never exposed through the document API:

- ``_auth.users``   -- one record per account, keyed by username (``_id``).
- ``_auth.grants``  -- one record per grant (see ``authz`` for the shape).
"""

from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from .errors import EmailAlreadyExists, UserAlreadyExists, UserNotFound

# Reserved database that holds auth data; never addressable via the document API.
AUTH_DB = "_auth"

_USERS = "users"
_GRANTS = "grants"


class AuthStore:
    def __init__(self, client):
        """:param client: a pymongo-compatible ``MongoClient`` (or mongomock)."""
        self._client = client

    @property
    def _users(self):
        return self._client[AUTH_DB][_USERS]

    @property
    def _grants(self):
        return self._client[AUTH_DB][_GRANTS]

    # -- users ---------------------------------------------------------------

    def create_user(
        self,
        username: str,
        password_hash: str,
        email: str | None = None,
        role: str = "user",
        active: bool = True,
    ) -> dict:
        """Create an account.

        Raises ``UserAlreadyExists`` if the username is taken, or
        ``EmailAlreadyExists`` if the email is already in use.
        """
        if self._users.find_one({"_id": username}) is not None:
            raise UserAlreadyExists(f"User '{username}' already exists.")
        if email is not None and self._users.find_one({"email": email}) is not None:
            raise EmailAlreadyExists(f"Email '{email}' is already in use.")
        record = {
            "_id": username,
            "password_hash": password_hash,
            "email": email,
            "role": role,
            "active": active,
        }
        self._users.insert_one(record)
        return self._public_user(record)

    def get_user(self, username: str) -> dict | None:
        """Return the raw user record (including ``password_hash``) or ``None``."""
        record = self._users.find_one({"_id": username})
        if record is None:
            return None
        return {"username": record["_id"], **{k: v for k, v in record.items() if k != "_id"}}

    def list_users(self) -> list[dict]:
        """Return all accounts in the public representation (no password hash)."""
        return [self._public_user(r) for r in self._users.find().sort("_id", 1)]

    def update_user(self, username: str, **fields: Any) -> dict:
        """Update mutable user fields (``role``, ``active``, ``email``).

        Raises ``UserNotFound`` if the user is missing, or ``EmailAlreadyExists``
        if a new email is already held by a *different* user.
        """
        allowed = {k: v for k, v in fields.items() if k in ("role", "active", "email")}
        if allowed.get("email") is not None:
            clash = self._users.find_one(
                {"email": allowed["email"], "_id": {"$ne": username}}
            )
            if clash is not None:
                raise EmailAlreadyExists(f"Email '{allowed['email']}' is already in use.")
        result = self._users.update_one({"_id": username}, {"$set": allowed})
        if result.matched_count == 0:
            raise UserNotFound(f"User '{username}' does not exist.")
        return self._public_user(self._users.find_one({"_id": username}))

    def set_password(self, username: str, password_hash: str) -> None:
        """Replace a user's password hash. Raises if the user is missing."""
        result = self._users.update_one(
            {"_id": username}, {"$set": {"password_hash": password_hash}}
        )
        if result.matched_count == 0:
            raise UserNotFound(f"User '{username}' does not exist.")

    def delete_user(self, username: str) -> None:
        """Delete an account and every grant belonging to it."""
        result = self._users.delete_one({"_id": username})
        if result.deleted_count == 0:
            raise UserNotFound(f"User '{username}' does not exist.")
        self._grants.delete_many({"username": username})

    def count_users(self) -> int:
        return self._users.count_documents({})

    def count_admins(self) -> int:
        return self._users.count_documents({"role": "admin"})

    # -- grants --------------------------------------------------------------

    def grants_for(self, username: str) -> list[dict]:
        """Return every grant held by ``username`` in the public shape."""
        return [self._public_grant(g) for g in self._grants.find({"username": username})]

    def add_grant(
        self,
        username: str,
        database: str | None,
        collection: str | None,
        doc_id: str | None,
        perms: list[str],
        granted_by: str,
    ) -> dict:
        """Create a grant for ``username`` and return it in the public shape."""
        record = {
            "username": username,
            "database": database,
            "collection": collection,
            "doc_id": doc_id,
            "perms": list(perms),
            "granted_by": granted_by,
        }
        result = self._grants.insert_one(record)
        record["_id"] = result.inserted_id
        return self._public_grant(record)

    def grant_owner(
        self,
        username: str,
        database: str | None,
        collection: str | None,
        doc_id: str | None,
        perms: list[str],
    ) -> None:
        """Idempotently give ``username`` full perms on a resource they created.

        Used for ownership auto-grants; a no-op if an identical scope already
        grants those perms so re-creation paths do not pile up duplicates.
        """
        existing = self._grants.find_one(
            {
                "username": username,
                "database": database,
                "collection": collection,
                "doc_id": doc_id,
            }
        )
        if existing is not None:
            merged = sorted(set(existing.get("perms", [])) | set(perms))
            self._grants.update_one({"_id": existing["_id"]}, {"$set": {"perms": merged}})
            return
        self.add_grant(username, database, collection, doc_id, perms, granted_by=username)

    def delete_grant(self, grant_id: str) -> None:
        """Delete a grant by its string id. Missing ids are silently ignored."""
        try:
            oid = ObjectId(grant_id)
        except (InvalidId, TypeError):
            return
        self._grants.delete_one({"_id": oid})

    # -- serialisation -------------------------------------------------------

    @staticmethod
    def _public_user(record: dict) -> dict:
        return {
            "username": record["_id"],
            "email": record.get("email"),
            "role": record.get("role", "user"),
            "active": record.get("active", True),
        }

    @staticmethod
    def _public_grant(record: dict) -> dict:
        return {
            "id": str(record["_id"]),
            "username": record["username"],
            "database": record.get("database"),
            "collection": record.get("collection"),
            "doc_id": record.get("doc_id"),
            "perms": record.get("perms", []),
            "granted_by": record.get("granted_by"),
        }
