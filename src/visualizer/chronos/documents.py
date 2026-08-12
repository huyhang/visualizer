"""Scope-keyed documents with revisions -- the mechanics both Chronos stores share.

Chronos keeps two kinds of record, and they differ only in what they hang off.
Books, plotlines and events are scoped to a **book**; library calendars are
scoped to their **owner**. Everything else about them is identical: a composite
``"<scope>::<id>"`` key, optimistic concurrency through ``_rev``, an author
stamp, a clock injected for deterministic tests, and a ``_public`` shape that
hides the fields the store owns.

That sameness used to be spelled out once inside ``StoryStore``. Pulling it out
here is what lets a second seam exist without a second copy of the revision
logic -- the part where a subtle divergence would be least visible and most
expensive.

This module holds no domain rules whatsoever. It does not know what a book is.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .errors import AlreadyExists, RevisionConflict

# Fields the store owns; never part of a caller's body. The scope field (``book``
# or ``owner``) is added per-collection, since only the caller names it.
_INTERNAL = {"_id", "_rev", "_deleted", "id", "created_by", "updated_by", "updated_at"}


def default_clock() -> datetime:
    return datetime.now(UTC)


class ScopedDocuments:
    """One Mongo collection of documents keyed by ``(scope, id)``.

    :param collection: a pymongo-compatible collection (or mongomock).
    :param scope_field: what the scope is called in the stored and public
        document -- ``"book"`` for story records, ``"owner"`` for the library.
    :param clock: returns the current time; injected for deterministic tests.
    """

    def __init__(
        self,
        collection,
        scope_field: str,
        clock: Callable[[], datetime] | None = None,
    ):
        self._coll = collection
        self._scope_field = scope_field
        self._clock = clock or default_clock
        self._internal = _INTERNAL | {scope_field}

    # -- shaping -------------------------------------------------------------

    @staticmethod
    def _key(scope: str, local_id: str) -> str:
        return f"{scope}::{local_id}"

    def public(self, stored: dict) -> dict:
        body = {k: v for k, v in stored.items() if k not in self._internal}
        return {
            "id": stored["id"],
            self._scope_field: stored[self._scope_field],
            "rev": stored["_rev"],
            "created_by": stored.get("created_by"),
            "updated_by": stored.get("updated_by"),
            **body,
        }

    def _stamped(self, scope, local_id, body, rev, created_by, author) -> dict:
        return {
            **body,
            "_id": self._key(scope, local_id),
            self._scope_field: scope,
            "id": local_id,
            "_rev": rev,
            "created_by": created_by,
            "updated_by": author,
            "updated_at": self._clock().isoformat(),
        }

    # -- reads ---------------------------------------------------------------

    def find(self, scope: str, local_id: str, not_found) -> dict:
        """The raw stored document, or raise ``not_found``."""
        stored = self._coll.find_one({"_id": self._key(scope, local_id)})
        if stored is None:
            raise not_found(f"'{local_id}' not found in '{scope}'.")
        return stored

    def get(self, scope: str, local_id: str, not_found) -> dict:
        return self.public(self.find(scope, local_id, not_found))

    def list_in_scope(self, scope: str) -> list[dict]:
        cursor = self._coll.find({self._scope_field: scope}).sort("id", 1)
        return [self.public(s) for s in cursor]

    def list_all(self) -> list[dict]:
        cursor = self._coll.find().sort([(self._scope_field, 1), ("id", 1)])
        return [self.public(s) for s in cursor]

    # -- revisions -----------------------------------------------------------

    @staticmethod
    def _compare_rev(current: dict, expected_rev: int | None) -> None:
        if expected_rev is not None and current["_rev"] != expected_rev:
            raise RevisionConflict(
                f"Modified since revision {expected_rev}; reload and retry.",
                evidence={"expected": expected_rev, "actual": current["_rev"]},
            )

    def check_rev(self, scope: str, local_id: str, expected_rev, not_found) -> None:
        """Raise unless the document is still at ``expected_rev``; no-op when None.

        Lets a caller test the precondition *before* starting work it could not
        undo -- a cascading delete has no transaction behind it.
        """
        self._compare_rev(self.find(scope, local_id, not_found), expected_rev)

    # -- writes --------------------------------------------------------------

    def insert(self, scope: str, local_id: str, body: dict, author=None) -> dict:
        stored = self._stamped(scope, local_id, body, 1, author, author)
        try:
            self._coll.insert_one(stored)
        except DuplicateKeyError:
            raise AlreadyExists(f"'{local_id}' already exists in '{scope}'.")
        return self.public(stored)

    def replace(
        self, scope: str, local_id: str, body: dict, expected_rev, author, not_found
    ) -> dict:
        current = self.find(scope, local_id, not_found)
        self._compare_rev(current, expected_rev)
        replacement = self._stamped(
            scope, local_id, body, current["_rev"] + 1, current.get("created_by"), author
        )
        updated = self._coll.find_one_and_replace(
            {"_id": current["_id"], "_rev": current["_rev"]},
            replacement,
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:  # changed between our read and this write
            raise RevisionConflict("Modified concurrently; reload and retry.")
        return self.public(updated)

    def remove(self, scope: str, local_id: str, expected_rev, author, not_found) -> None:
        current = self.find(scope, local_id, not_found)
        self._compare_rev(current, expected_rev)
        result = self._coll.delete_one({"_id": current["_id"], "_rev": current["_rev"]})
        if result.deleted_count == 0:
            raise RevisionConflict("Modified concurrently; reload and retry.")
