"""Scope-keyed documents with revisions -- the mechanics the stores share.

Every service here keeps records that differ only in what they hang off. Chronos
books, plotlines and events are scoped to a **book**; its library calendars are
scoped to their **owner**; Prithvi maps are scoped to a **world** and its pins to
a map. Everything else about them is identical: a composite key, optimistic
concurrency through ``_rev``, an author stamp, a clock injected for deterministic
tests, and a public shape that hides the fields the store owns.

That sameness used to be spelled out once inside ``StoryStore``. Pulling it out
is what lets a second seam exist without a second copy of the revision logic --
the part where a subtle divergence would be least visible and most expensive.
It lived under ``chronos`` while chronos was its only caller; it moved up here
when Prithvi needed the same guarantees, rather than growing a third copy.

Two storage policies sit on those shared mechanics, because the two services want
genuinely different things:

- ``ScopedDocuments`` -- the body lives in the record, deletes are hard, and an
  id may be reused immediately. What articles-sized documents want.
- ``VersionedDocuments`` -- each revision's body is its own record behind a small
  head pointer, deletes leave a tombstone, and recent revisions are retained.
  What map-sized documents want: a 5 MiB SVG multiplied by its history would
  breach MongoDB's 16 MiB per-document ceiling long before anyone noticed.

This module holds no domain rules whatsoever. It does not know what a book is,
and it does not know what a map is. Both policies take the error classes they
raise from their caller for the same reason: the vocabulary of a failure belongs
to the service, not to the mechanism.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

# Fields the store owns; never part of a caller's body. The scope field (``book``
# or ``owner``) is added per-collection, since only the caller names it.
_INTERNAL = {"_id", "_rev", "_deleted", "id", "created_by", "updated_by", "updated_at"}

CREATE = "create"
UPDATE = "update"
DELETE = "delete"
RESTORE = "restore"


def default_clock() -> datetime:
    return datetime.now(UTC)


def composite_key(parts: Sequence[str]) -> str:
    """The stored ``_id`` for an identity: its parts, in order, joined.

    Callers validate their own identifiers; nothing here rejects a part that
    contains the separator, exactly as the two-part key never did.
    """
    return "::".join(parts)


class ScopedDocuments:
    """One Mongo collection of documents keyed by ``(scope, id)``.

    :param collection: a pymongo-compatible collection (or mongomock).
    :param scope_field: what the scope is called in the stored and public
        document -- ``"book"`` for story records, ``"owner"`` for the library.
    :param clock: returns the current time; injected for deterministic tests.
    :param already_exists: raised when an insert collides with a live record.
    :param conflict: raised when a write loses to a concurrent one.
    """

    def __init__(
        self,
        collection,
        scope_field: str,
        clock: Callable[[], datetime] | None = None,
        *,
        already_exists,
        conflict,
    ):
        self._coll = collection
        self._scope_field = scope_field
        self._clock = clock or default_clock
        self._internal = _INTERNAL | {scope_field}
        self._already_exists = already_exists
        self._conflict = conflict

    # -- shaping -------------------------------------------------------------

    @staticmethod
    def _key(scope: str, local_id: str) -> str:
        return composite_key((scope, local_id))

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

    def _compare_rev(self, current: dict, expected_rev: int | None) -> None:
        if expected_rev is not None and current["_rev"] != expected_rev:
            raise self._conflict(
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
            raise self._already_exists(f"'{local_id}' already exists in '{scope}'.")
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
            raise self._conflict("Modified concurrently; reload and retry.")
        return self.public(updated)

    def remove(self, scope: str, local_id: str, expected_rev, author, not_found) -> None:
        current = self.find(scope, local_id, not_found)
        self._compare_rev(current, expected_rev)
        result = self._coll.delete_one({"_id": current["_id"], "_rev": current["_rev"]})
        if result.deleted_count == 0:
            raise self._conflict("Modified concurrently; reload and retry.")


class VersionedDocuments:
    """Records whose revision bodies are stored beside them, not inside them.

    Two collections. The *head* is one small document per record: its identity,
    the revision number, a pointer at the current body, and whether it is a
    tombstone. Each *revision* is its own document holding one body and a pointer
    at the revision before it.

    Writing is deliberately ordered: the new revision is inserted first, and only
    then does the head move -- and only if the head is still the one the caller
    read. A writer that loses the race deletes the candidate it inserted; a
    process that dies mid-write can at worst leave a revision nothing points at.
    Neither can leave a head pointing at a body that does not exist, which is the
    one failure that would be unrecoverable.

    Deleting writes a tombstone rather than removing the record, and creating the
    same identity again revives it as the next revision. That keeps the ordinary
    lifecycle -- place a pin, remove it, place it again -- working as a plain
    create, while ``restore`` remains available for undoing a delete outright.

    :param heads: pymongo-compatible collection for the head documents.
    :param revisions: pymongo-compatible collection for the revision bodies.
    :param identity_fields: the ordered field names that name one record, e.g.
        ``("world", "map")``. Stored on both documents so callers -- and the
        storage accounting -- can read an identity back without parsing keys.
    :param keep: how many recent revisions to retain per record.
    :param clock: returns the current time; injected for deterministic tests.
    :param conflict: raised when a write loses to a concurrent one.
    :param gone: raised when a revision is asked for that is no longer retained.
    """

    def __init__(
        self,
        heads,
        revisions,
        identity_fields: tuple[str, ...],
        keep: int,
        clock: Callable[[], datetime] | None = None,
        *,
        conflict,
        gone,
    ):
        if keep < 1:
            raise ValueError("keep must be at least 1.")
        self._heads = heads
        self._revisions = revisions
        self._fields = identity_fields
        self._keep = keep
        self._clock = clock or default_clock
        self._conflict = conflict
        self._gone = gone
        self._heads.create_index([(field, 1) for field in identity_fields])
        self._revisions.create_index([("resource_key", 1), ("rev", -1)])

    # -- reads ---------------------------------------------------------------

    def get(self, identity: dict, not_found) -> dict:
        head = self._live_head(identity, not_found)
        return self._public(head, self._body_of(head))

    def list(self, filters: dict) -> list[dict]:
        """Every live record matching ``filters``, in identity order.

        One query for the heads and one for their bodies, rather than one per
        record: a world with fifty maps should not cost fifty round trips.
        """
        heads = list(
            self._heads.find(
                {**filters, "deleted": False, "moving_to": {"$exists": False}}
            )
        )
        if not heads:
            return []
        ids = [head["current_revision"] for head in heads]
        bodies = {r["_id"]: r for r in self._revisions.find({"_id": {"$in": ids}})}
        rows = [self._public(h, bodies[h["current_revision"]]) for h in heads]
        return sorted(rows, key=lambda row: tuple(row[f] for f in self._fields))

    def count(self, filters: dict) -> int:
        return self._heads.count_documents(
            {**filters, "deleted": False, "moving_to": {"$exists": False}}
        )

    def identity_exists(self, identity: dict) -> bool:
        """Whether an identity is reserved, including by a retained tombstone."""
        return self._heads.find_one({"_id": self._key(identity)}, {"_id": 1}) is not None

    def history(self, identity: dict, not_found) -> list[dict]:
        """Retained revisions, newest first, including a delete."""
        head = self._any_head(identity, not_found)
        return [self._meta(r) for r in self._chain(head)]

    def revision(self, identity: dict, rev: int, not_found) -> dict:
        head = self._any_head(identity, not_found)
        found = self._retained(head, rev)
        return {**identity, **self._meta(found), **(found.get("body") or {})}

    # -- writes --------------------------------------------------------------

    def create(self, identity: dict, body: dict, author: str, already_exists) -> dict:
        """Insert a record, or revive one whose name was freed by a delete."""
        head = self._heads.find_one({"_id": self._key(identity)})
        if head is not None and not head.get("deleted"):
            raise already_exists(f"'{self._label(identity)}' already exists.")
        if head is not None:
            return self._advance(head, body, CREATE, head["rev"], author)
        return self._first(identity, body, author, already_exists)

    def update(self, identity: dict, body: dict, expected_rev, author, not_found) -> dict:
        head = self._live_head(identity, not_found)
        return self._advance(head, body, UPDATE, expected_rev, author)

    def delete(self, identity: dict, expected_rev, author, not_found) -> None:
        head = self._live_head(identity, not_found)
        self._advance(head, None, DELETE, expected_rev, author)

    def relocate(
        self,
        identity: dict,
        destination: dict,
        expected_rev,
        author,
        not_found,
        already_exists,
    ) -> dict:
        """Move a live record to another composite identity without losing history.

        The head is locked before its replacement is inserted.  Ordinary writes
        include that lock in their compare-and-swap, so prose cannot change while
        its revision chain is being re-keyed.  Each step is repeatable: a caller
        may resume after an interrupted request by presenting the same source and
        destination.

        **The revision number does not change.**  A move re-addresses a record; it
        does not edit it.  Advancing the revision would append a body identical to
        the one before it and spend one of the retained slots that belong to the
        prose -- at ``keep`` revisions, a well-organised book would lose its whole
        editing history to its filing.  A caller that needs a record of the move
        keeps one of its own.
        """
        source_key = self._key(identity)
        destination_key = self._key(destination)
        if source_key == destination_key:
            return self.get(identity, not_found)

        source = self._heads.find_one({"_id": source_key})
        if source is None or source.get("deleted"):
            return self._already_relocated(identity, destination_key, not_found)
        self._lock_for_move(source, destination_key, expected_rev)
        target = self._destination_head(
            source, destination, destination_key, author, already_exists
        )
        if target.get("deleted") or (
            target["current_revision"] != source["current_revision"]
        ):
            self._release_move_lock(source_key, destination_key)
            raise already_exists(f"'{self._label(destination)}' already exists.")
        self._rekey_revisions(source_key, destination_key, destination)
        self._heads.delete_one({"_id": source_key, "moving_to": destination_key})
        return self._public(target, self._body_of(target))

    def _already_relocated(self, identity: dict, destination_key: str, not_found) -> dict:
        """A move whose source is gone: it finished already, or was never there."""
        target = self._heads.find_one({"_id": destination_key})
        if target is not None and not target.get("deleted"):
            return self._public(target, self._body_of(target))
        raise not_found(f"'{self._label(identity)}' was not found.")

    def _lock_for_move(self, source: dict, destination_key: str, expected_rev) -> None:
        """Claim the head for this destination, or refuse to touch it.

        Idempotent on purpose: a resumed request meets its own claim and passes
        through, while a claim pointing somewhere else is a conflict rather than
        a second move racing the first.
        """
        moving_to = source.get("moving_to")
        if moving_to == destination_key:
            return
        if moving_to is not None:
            raise self._conflict("The resource is already being moved elsewhere.")
        if source["rev"] != expected_rev:
            raise self._conflict(
                f"Modified since revision {expected_rev}; reload and retry.",
                evidence={"expected": expected_rev, "actual": source["rev"]},
            )
        locked = self._heads.update_one(
            {
                "_id": source["_id"],
                "rev": expected_rev,
                "deleted": False,
                "moving_to": {"$exists": False},
            },
            {"$set": {"moving_to": destination_key}},
        )
        if locked.matched_count == 0:
            raise self._conflict("Modified concurrently; reload and retry.")
        source["moving_to"] = destination_key

    def _destination_head(
        self, source: dict, destination: dict, destination_key: str, author,
        already_exists,
    ) -> dict:
        """The head at the destination: the copy this move makes, or one already there."""
        existing = self._heads.find_one({"_id": destination_key})
        if existing is not None:
            return existing
        moved = {
            **source,
            "_id": destination_key,
            **destination,
            "updated_by": author,
            "updated_at": self._now(),
        }
        moved.pop("moving_to", None)
        try:
            self._heads.insert_one(moved)
        except DuplicateKeyError as exc:
            raced = self._heads.find_one({"_id": destination_key})
            if raced is None:
                raise already_exists(
                    f"'{self._label(destination)}' already exists."
                ) from exc
            return raced
        return moved

    def _release_move_lock(self, source_key: str, destination_key: str) -> None:
        self._heads.update_one(
            {"_id": source_key, "moving_to": destination_key},
            {"$unset": {"moving_to": ""}},
        )

    def _rekey_revisions(
        self, source_key: str, destination_key: str, destination: dict
    ) -> None:
        self._revisions.update_many(
            {"resource_key": source_key},
            {"$set": {"resource_key": destination_key, **destination}},
        )

    def restore(
        self, identity: dict, rev: int, expected_rev, author, not_found,
        transform=None,
    ) -> dict:
        """Re-apply a retained revision as a new one, tombstone or not."""
        head = self._any_head(identity, not_found)
        target = self._retained(head, rev)
        if target.get("body") is None:
            raise self._gone(f"Revision {rev} is a deletion and has no body.")
        body = target["body"]
        if transform is not None:
            body = transform(dict(body))
        return self._advance(head, body, RESTORE, expected_rev, author)

    # -- internals -----------------------------------------------------------

    def _first(self, identity: dict, body: dict, author, already_exists) -> dict:
        key = self._key(identity)
        moment = self._now()
        revision = self._revision(key, identity, 1, None, CREATE, body, author, moment)
        self._revisions.insert_one(revision)
        head = {
            "_id": key,
            **identity,
            "rev": 1,
            "current_revision": revision["_id"],
            "deleted": False,
            "created_by": author,
            "updated_by": author,
            "updated_at": moment,
        }
        try:
            self._heads.insert_one(head)
        except DuplicateKeyError as exc:
            # Someone inserted the same identity between our read and this write.
            self._revisions.delete_one({"_id": revision["_id"]})
            raise already_exists(f"'{self._label(identity)}' already exists.") from exc
        return self._public(head, revision)

    def _advance(self, head, body, op, expected_rev, author) -> dict:
        """Append a revision and move the head onto it, or lose the race."""
        if expected_rev is not None and head["rev"] != expected_rev:
            raise self._conflict(
                f"Modified since revision {expected_rev}; reload and retry.",
                evidence={"expected": expected_rev, "actual": head["rev"]},
            )
        identity = {field: head[field] for field in self._fields}
        rev = head["rev"] + 1
        moment = self._now()
        revision = self._revision(
            head["_id"], identity, rev, head["current_revision"], op, body, author, moment
        )
        self._revisions.insert_one(revision)
        moved = self._heads.update_one(
            {
                "_id": head["_id"],
                "rev": head["rev"],
                "moving_to": {"$exists": False},
            },
            {
                "$set": {
                    "rev": rev,
                    "current_revision": revision["_id"],
                    "deleted": body is None,
                    "updated_by": author,
                    "updated_at": moment,
                }
            },
        )
        if moved.matched_count == 0:
            self._revisions.delete_one({"_id": revision["_id"]})
            raise self._conflict("Modified concurrently; reload and retry.")
        self._prune(head["_id"], rev)
        advanced = {
            **head,
            "rev": rev,
            "current_revision": revision["_id"],
            "deleted": body is None,
            "updated_by": author,
            "updated_at": moment,
        }
        return self._public(advanced, revision)

    def _prune(self, key: str, current_rev: int) -> None:
        cutoff = current_rev - self._keep
        if cutoff >= 1:
            self._revisions.delete_many({"resource_key": key, "rev": {"$lte": cutoff}})

    def _revision(self, key, identity, rev, parent, op, body, author, moment) -> dict:
        return {
            "_id": ObjectId(),
            "resource_key": key,
            **identity,
            "rev": rev,
            "parent": parent,
            "op": op,
            "body": body,
            "author": author,
            "timestamp": moment,
        }

    def _live_head(self, identity: dict, not_found) -> dict:
        head = self._any_head(identity, not_found)
        if head.get("deleted"):
            raise not_found(f"'{self._label(identity)}' was not found.")
        if head.get("moving_to"):
            raise self._conflict("The resource is being moved; retry shortly.")
        return head

    def _any_head(self, identity: dict, not_found) -> dict:
        head = self._heads.find_one({"_id": self._key(identity)})
        if head is None:
            raise not_found(f"'{self._label(identity)}' was not found.")
        return head

    def _body_of(self, head) -> dict:
        revision = self._revisions.find_one({"_id": head["current_revision"]})
        if revision is None:
            # Only reachable if a revision were deleted out from under a live
            # head, which the write ordering above is designed to prevent.
            raise RuntimeError(f"Head '{head['_id']}' points at a missing revision.")
        return revision

    def _chain(self, head):
        """Walk back from the current revision, newest first, while retained."""
        revision = self._body_of(head)
        for _ in range(self._keep):
            yield revision
            parent = revision.get("parent")
            if parent is None:
                return
            revision = self._revisions.find_one({"_id": parent})
            if revision is None:
                return

    def _retained(self, head, rev: int) -> dict:
        found = next((r for r in self._chain(head) if r["rev"] == rev), None)
        if found is None:
            raise self._gone(f"Revision {rev} is no longer retained.")
        return found

    def _public(self, head, revision) -> dict:
        return {
            **{field: head[field] for field in self._fields},
            "rev": head["rev"],
            "created_by": head.get("created_by"),
            "updated_by": head.get("updated_by"),
            "updated_at": head.get("updated_at"),
            **(revision.get("body") or {}),
        }

    @staticmethod
    def _meta(revision) -> dict:
        return {
            "rev": revision["rev"],
            "op": revision["op"],
            "author": revision.get("author"),
            "timestamp": revision["timestamp"],
            "deleted": revision.get("body") is None,
        }

    def _key(self, identity: dict) -> str:
        return composite_key([identity[field] for field in self._fields])

    def _label(self, identity: dict) -> str:
        return "/".join(str(identity[field]) for field in self._fields)

    def _now(self) -> str:
        return self._clock().isoformat()
