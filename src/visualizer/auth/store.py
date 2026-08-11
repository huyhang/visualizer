"""Persistence layer for user accounts and access-control grants.

``AuthStore`` is to authentication what ``DocumentStore`` is to documents: the
single seam between the app and MongoDB. It receives its Mongo client via the
constructor (inversion of control) so tests inject an in-memory client and
production injects a real one -- the same pattern, and often the *same* client,
as ``DocumentStore``.

Everything it owns lives in a dedicated, reserved database (``_auth``) that is
never exposed through the document API:

- ``_auth.users``    -- one record per account, keyed by username (``_id``).
- ``_auth.grants``   -- one record per grant (see ``authz`` for the shape).
- ``_auth.settings`` -- singleton records for instance-wide settings (e.g. the
  registration mode), keyed by setting name (``_id``).
"""

from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from .errors import EmailAlreadyExists, UserAlreadyExists, UserNotFound

# Reserved database that holds auth data; never addressable via the document API.
AUTH_DB = "_auth"

_USERS = "users"
_GRANTS = "grants"
_SETTINGS = "settings"
_CONTACTS = "contacts"

# Grants are namespaced by the kind of resource they scope, so services sharing
# this store never match one another's resources (a chronos book named "x" must
# not grant access to a akasha database named "x"). See ``authz``.
DATABASE_RESOURCE = "database"

# Registration modes. ``open`` lets anyone self-register; ``invite`` disables the
# registration page so accounts exist only when an admin creates them.
REGISTRATION_OPEN = "open"
REGISTRATION_INVITE = "invite"
REGISTRATION_MODES = (REGISTRATION_OPEN, REGISTRATION_INVITE)

# The settings record id holding the current registration mode.
_REGISTRATION_MODE_KEY = "registration_mode"


def registration_allowed(mode: str, user_count: int) -> bool:
    """Whether a new self-registration may proceed (pure policy).

    ``open`` mode always allows it. ``invite`` mode blocks it -- *except* when
    there are no users yet, so a fresh deployment can still bootstrap its first
    (admin) account even if it starts invite-only.
    """
    return mode == REGISTRATION_OPEN or user_count == 0


def _type_query(resource_type: str):
    """Match a resource_type, treating a missing field as the legacy default.

    Grants written before this field existed are akasha grants.
    """
    if resource_type == DATABASE_RESOURCE:
        return {"$in": [DATABASE_RESOURCE, None]}
    return resource_type


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

    @property
    def _settings(self):
        return self._client[AUTH_DB][_SETTINGS]

    @property
    def _contacts(self):
        return self._client[AUTH_DB][_CONTACTS]

    # -- settings ------------------------------------------------------------

    def get_registration_mode(self) -> str:
        """Return the current registration mode (defaults to ``open``)."""
        record = self._settings.find_one({"_id": _REGISTRATION_MODE_KEY})
        return (record or {}).get("value", REGISTRATION_OPEN)

    def set_registration_mode(self, mode: str) -> None:
        """Persist the registration mode. Raises ``ValueError`` for unknown modes."""
        if mode not in REGISTRATION_MODES:
            raise ValueError(f"Unknown registration mode: {mode!r}.")
        self._settings.update_one(
            {"_id": _REGISTRATION_MODE_KEY}, {"$set": {"value": mode}}, upsert=True
        )

    # -- users ---------------------------------------------------------------

    def create_user(
        self,
        username: str,
        password_hash: str,
        email: str | None = None,
        role: str = "user",
        active: bool = True,
        must_change_password: bool = False,
    ) -> dict:
        """Create an account.

        ``must_change_password`` forces the user to set a new password on their
        next login (used for admin-provisioned accounts).

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
            "must_change_password": must_change_password,
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
        allowed = {
            k: v
            for k, v in fields.items()
            if k in ("role", "active", "email", "must_change_password")
        }
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

    def set_password(
        self, username: str, password_hash: str, must_change_password: bool = False
    ) -> None:
        """Replace a user's password hash and set the must-change flag.

        A voluntary/first-login change passes ``False`` (clears the flag); an
        admin-initiated reset passes ``True`` so the user is forced to change it
        again on their next login. Raises if the user is missing.
        """
        result = self._users.update_one(
            {"_id": username},
            {
                "$set": {
                    "password_hash": password_hash,
                    "must_change_password": must_change_password,
                }
            },
        )
        if result.matched_count == 0:
            raise UserNotFound(f"User '{username}' does not exist.")

    def delete_user(self, username: str) -> None:
        """Delete an account and every trace of it: its grants, its own
        collaborator roster, and any reference to it in *other* users' rosters."""
        result = self._users.delete_one({"_id": username})
        if result.deleted_count == 0:
            raise UserNotFound(f"User '{username}' does not exist.")
        self._grants.delete_many({"username": username})
        self._contacts.delete_one({"_id": username})
        self._contacts.update_many({}, {"$pull": {"contacts": username}})

    def count_users(self) -> int:
        return self._users.count_documents({})

    def count_admins(self) -> int:
        return self._users.count_documents({"role": "admin"})

    # -- grants --------------------------------------------------------------

    def grants_for(self, username: str) -> list[dict]:
        """Return every grant held by ``username`` in the public shape."""
        return [self._public_grant(g) for g in self._grants.find({"username": username})]

    def grants_on(
        self,
        database: str | None,
        collection: str | None,
        doc_id: str | None,
        resource_type: str = DATABASE_RESOURCE,
    ) -> list[dict]:
        """Return every grant scoped to *exactly* this resource (any user).

        Matches the scope fields verbatim -- ``None`` means the wildcard scope,
        not "any value" -- so it answers "who has been granted access to this
        specific collection/document?" for the sharing UI. ``resource_type`` is
        namespaced like everywhere else, so akasha and chronos grants that share
        a name never bleed together.
        """
        query = {
            "resource_type": _type_query(resource_type),
            "database": database,
            "collection": collection,
            "doc_id": doc_id,
        }
        return [self._public_grant(g) for g in self._grants.find(query)]

    def delete_grants_on(
        self,
        database: str | None,
        collection: str | None,
        doc_id: str | None,
        resource_type: str = DATABASE_RESOURCE,
    ) -> int:
        """Delete every grant scoped to *exactly* this resource; return how many.

        The write-side twin of ``grants_on``, matching the scope fields the same
        verbatim way, in one query rather than a read followed by a delete per
        grant. Used when a resource is destroyed: ids may be reused, so a grant
        left behind is a grant on a *name*, and would attach itself to whatever
        is created under that name next.
        """
        result = self._grants.delete_many(
            {
                "resource_type": _type_query(resource_type),
                "database": database,
                "collection": collection,
                "doc_id": doc_id,
            }
        )
        return result.deleted_count

    def add_grant(
        self,
        username: str,
        database: str | None,
        collection: str | None,
        doc_id: str | None,
        perms: list[str],
        granted_by: str,
        resource_type: str = DATABASE_RESOURCE,
    ) -> dict:
        """Create a grant for ``username`` and return it in the public shape.

        ``resource_type`` namespaces the scope so different services' grants
        never match each other's resources (see ``authz``). It defaults to
        ``"database"``, which is what akasha grants are.
        """
        record = {
            "username": username,
            "resource_type": resource_type,
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
        resource_type: str = DATABASE_RESOURCE,
    ) -> None:
        """Idempotently give ``username`` full perms on a resource they created.

        Used for ownership auto-grants; a no-op if an identical scope already
        grants those perms so re-creation paths do not pile up duplicates.
        """
        existing = self._grants.find_one(
            {
                "username": username,
                "resource_type": _type_query(resource_type),
                "database": database,
                "collection": collection,
                "doc_id": doc_id,
            }
        )
        if existing is not None:
            merged = sorted(set(existing.get("perms", [])) | set(perms))
            self._grants.update_one({"_id": existing["_id"]}, {"$set": {"perms": merged}})
            return
        self.add_grant(
            username, database, collection, doc_id, perms,
            granted_by=username, resource_type=resource_type,
        )

    def delete_grant(self, grant_id: str) -> None:
        """Delete a grant by its string id. Missing ids are silently ignored."""
        try:
            oid = ObjectId(grant_id)
        except (InvalidId, TypeError):
            return
        self._grants.delete_one({"_id": oid})

    # -- collaborator roster (per-user "address book") -----------------------

    def list_contacts(self, owner: str) -> list[str]:
        """Return ``owner``'s saved collaborators, sorted.

        Filtered to accounts that still exist, so a roster never offers a user
        who has since been deleted (a belt-and-braces guard alongside the
        cleanup in ``delete_user``).
        """
        record = self._contacts.find_one({"_id": owner})
        names = (record or {}).get("contacts", [])
        if not names:
            return []
        existing = {u["_id"] for u in self._users.find({"_id": {"$in": names}}, {"_id": 1})}
        return sorted(n for n in names if n in existing)

    def add_contact(self, owner: str, username: str) -> None:
        """Add ``username`` to ``owner``'s roster (idempotent).

        Raises ``UserNotFound`` if the target account does not exist. The
        "not yourself" policy is enforced by the caller.
        """
        if self.get_user(username) is None:
            raise UserNotFound(f"User '{username}' does not exist.")
        self._contacts.update_one(
            {"_id": owner}, {"$addToSet": {"contacts": username}}, upsert=True
        )

    def remove_contact(self, owner: str, username: str) -> None:
        """Remove ``username`` from ``owner``'s roster (a no-op if absent)."""
        self._contacts.update_one({"_id": owner}, {"$pull": {"contacts": username}})

    # -- serialisation -------------------------------------------------------

    @staticmethod
    def _public_user(record: dict) -> dict:
        return {
            "username": record["_id"],
            "email": record.get("email"),
            "role": record.get("role", "user"),
            "active": record.get("active", True),
            "must_change_password": record.get("must_change_password", False),
        }

    @staticmethod
    def _public_grant(record: dict) -> dict:
        return {
            "id": str(record["_id"]),
            "username": record["username"],
            # Grants written before resource_type existed are akasha
            # (database-scoped) grants, so that is the backward-compatible default.
            "resource_type": record.get("resource_type") or DATABASE_RESOURCE,
            "database": record.get("database"),
            "collection": record.get("collection"),
            "doc_id": record.get("doc_id"),
            "perms": record.get("perms", []),
            "granted_by": record.get("granted_by"),
        }
