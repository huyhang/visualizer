"""Persistence layer for documents.

``DocumentStore`` is the single seam between the application and MongoDB. It
receives its Mongo client via the constructor (inversion of control) so tests
can inject an in-memory client while production injects a real one. It also
receives a ``clock`` (for deterministic version timestamps in tests) and
``versions_keep`` (the history cap), both injected -- the store never reads the
environment or the wall clock directly.

Documents are stored using the caller-supplied ``doc_id`` as the Mongo ``_id``.
Three fields are Mongo-internal and never leak to callers:

- ``_id``       -- the document id (surfaced separately as ``id``).
- ``_rev``      -- an optimistic-concurrency counter (surfaced as ``rev``).
- ``_history``  -- the last N version snapshots (see ``history``); surfaced only
  through the dedicated version helpers.

Writes are optimistically concurrent: an ``expected_rev`` guards updates/deletes
against lost updates, and every successful write appends a pruned snapshot in the
*same* atomic ``find_one_and_replace`` so the document and its history can never
diverge (important on a standalone MongoDB, which has no transactions). Deletes
are soft (a tombstone) so history stays diffable; a later ``create`` of the same
id revives it.
"""

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .errors import (
    CollectionAlreadyExists,
    CollectionNotFound,
    DatabaseNotFound,
    DocumentAlreadyExists,
    DocumentNotFound,
    RevisionConflict,
)
from .history import CREATE, DELETE, UPDATE, make_snapshot, prune

_DEFAULT_VERSIONS_KEEP = 20


def _default_clock() -> datetime:
    return datetime.now(UTC)


class DocumentStore:
    def __init__(
        self,
        client,
        clock: Callable[[], datetime] | None = None,
        versions_keep: int = _DEFAULT_VERSIONS_KEEP,
    ):
        """:param client: a pymongo-compatible ``MongoClient`` (or mongomock).
        :param clock: returns the current time; injected so tests are deterministic.
        :param versions_keep: max snapshots retained per document.
        """
        self._client = client
        self._clock = clock or _default_clock
        self._versions_keep = versions_keep

    def _collection(self, database: str, collection: str):
        return self._client[database][collection]

    def _now(self) -> str:
        return self._clock().isoformat()

    # -- namespace management ------------------------------------------------

    def create_collection(self, database: str, collection: str) -> dict:
        """Explicitly create a collection (and its database).

        MongoDB creates databases/collections lazily on first write; this makes
        it an explicit, up-front operation. Fails if the collection exists.
        """
        if self._collection_exists(database, collection):
            raise CollectionAlreadyExists(
                f"Collection '{collection}' already exists in database '{database}'."
            )
        self._client[database].create_collection(collection)
        return {"database": database, "collection": collection}

    def _database_exists(self, database: str) -> bool:
        return database in self._client.list_database_names()

    def _collection_exists(self, database: str, collection: str) -> bool:
        return collection in self._client[database].list_collection_names()

    def _require_namespace(self, database: str, collection: str) -> None:
        """Raise if the database or collection does not already exist."""
        if not self._database_exists(database):
            raise DatabaseNotFound(f"Database '{database}' does not exist.")
        if not self._collection_exists(database, collection):
            raise CollectionNotFound(
                f"Collection '{collection}' does not exist in database '{database}'."
            )

    # -- browse listings (grant filtering happens in the route layer) --------

    def list_databases(self) -> list[str]:
        """User-visible databases (reserved ``_``-prefixed ones are hidden)."""
        return sorted(
            d for d in self._client.list_database_names() if not d.startswith("_")
        )

    def list_collections(self, database: str) -> list[str]:
        if not self._database_exists(database):
            raise DatabaseNotFound(f"Database '{database}' does not exist.")
        return sorted(self._client[database].list_collection_names())

    def list_documents(
        self,
        database: str,
        collection: str,
        limit: int | None = None,
        after: str | None = None,
    ) -> list[dict]:
        """List live documents in id order, optionally paginated by ``after``."""
        self._require_namespace(database, collection)
        query: dict[str, Any] = {"_deleted": {"$ne": True}}
        if after is not None:
            query["_id"] = {"$gt": after}
        cursor = self._collection(database, collection).find(query).sort("_id", 1)
        if limit:
            cursor = cursor.limit(limit)
        return [self._to_public(stored) for stored in cursor]

    # -- (de)serialisation ---------------------------------------------------

    @staticmethod
    def _sanitize(document: dict) -> dict:
        """Drop reserved ``_``-prefixed keys so callers cannot inject internals."""
        return {k: v for k, v in document.items() if not k.startswith("_")}

    @staticmethod
    def _body(stored: dict) -> dict:
        """The public body: stored fields minus every internal ``_`` field."""
        return {k: v for k, v in stored.items() if not k.startswith("_")}

    @classmethod
    def _to_public(cls, stored: dict) -> dict:
        """Public representation of a stored document."""
        return {
            "id": stored["_id"],
            "document": cls._body(stored),
            "rev": stored.get("_rev", 1),
        }

    def _replacement(self, doc_id: str, body: dict, rev: int, history: list[dict]) -> dict:
        return {**body, "_id": doc_id, "_rev": rev, "_history": history}

    def _append_history(self, current: dict, snapshot: dict) -> list[dict]:
        return prune(list(current.get("_history", [])) + [snapshot], self._versions_keep)

    @staticmethod
    def _check_rev(current: dict, expected_rev: int | None) -> None:
        """Raise ``RevisionConflict`` when the caller's expected rev is stale."""
        if expected_rev is not None and current.get("_rev") != expected_rev:
            raise RevisionConflict(
                f"Document was modified since revision {expected_rev}; "
                "reload it and retry."
            )

    # -- writes --------------------------------------------------------------

    def create(
        self, database: str, collection: str, doc_id: str, document: dict, author: str | None = None
    ) -> dict:
        """Insert a new document (or revive a soft-deleted one).

        The database and collection must already exist. Fails with
        ``DocumentAlreadyExists`` if a *live* document has this id.
        """
        self._require_namespace(database, collection)
        body = self._sanitize(document)
        existing = self._collection(database, collection).find_one({"_id": doc_id})
        if existing is not None and not existing.get("_deleted"):
            raise DocumentAlreadyExists(
                f"Document '{doc_id}' already exists in '{database}/{collection}'."
            )
        if existing is not None:
            return self._revive(database, collection, doc_id, body, existing, author)
        return self._insert_new(database, collection, doc_id, body, author)

    def _insert_new(self, database, collection, doc_id, body, author) -> dict:
        rev = 1
        snapshot = make_snapshot(rev, CREATE, author, self._now(), body)
        stored = self._replacement(doc_id, body, rev, [snapshot])
        try:
            self._collection(database, collection).insert_one(stored)
        except DuplicateKeyError:
            raise DocumentAlreadyExists(
                f"Document '{doc_id}' already exists in '{database}/{collection}'."
            )
        return self._to_public(stored)

    def _revive(self, database, collection, doc_id, body, existing, author) -> dict:
        new_rev = existing.get("_rev", 1) + 1
        snapshot = make_snapshot(new_rev, CREATE, author, self._now(), body)
        replacement = self._replacement(
            doc_id, body, new_rev, self._append_history(existing, snapshot)
        )
        revived = self._collection(database, collection).find_one_and_replace(
            {"_id": doc_id, "_rev": existing.get("_rev")},
            replacement,
            return_document=ReturnDocument.AFTER,
        )
        if revived is None:  # someone changed/revived it first
            raise DocumentAlreadyExists(
                f"Document '{doc_id}' already exists in '{database}/{collection}'."
            )
        return self._to_public(revived)

    def update(
        self,
        database: str,
        collection: str,
        doc_id: str,
        document: dict,
        expected_rev: int | None = None,
        author: str | None = None,
    ) -> dict:
        """Fully replace an existing document (optimistically concurrent).

        Fails with ``DocumentNotFound`` if it does not exist, or
        ``RevisionConflict`` if ``expected_rev`` no longer matches the stored rev.
        """
        body = self._sanitize(document)
        current = self._require_live(database, collection, doc_id)
        self._check_rev(current, expected_rev)
        new_rev = current.get("_rev", 1) + 1
        snapshot = make_snapshot(new_rev, UPDATE, author, self._now(), body)
        replacement = self._replacement(
            doc_id, body, new_rev, self._append_history(current, snapshot)
        )
        return self._compare_and_replace(database, collection, doc_id, current, replacement)

    def delete(
        self,
        database: str,
        collection: str,
        doc_id: str,
        expected_rev: int | None = None,
        author: str | None = None,
    ) -> None:
        """Soft-delete a document (a tombstone), keeping its history diffable."""
        current = self._require_live(database, collection, doc_id)
        self._check_rev(current, expected_rev)
        new_rev = current.get("_rev", 1) + 1
        snapshot = make_snapshot(new_rev, DELETE, author, self._now(), None)
        replacement = {
            "_id": doc_id,
            "_rev": new_rev,
            "_deleted": True,
            "_history": self._append_history(current, snapshot),
        }
        self._compare_and_replace(database, collection, doc_id, current, replacement)

    def _require_live(self, database: str, collection: str, doc_id: str) -> dict:
        """Return the current stored doc or raise if it is missing/deleted."""
        current = self._collection(database, collection).find_one({"_id": doc_id})
        if current is None or current.get("_deleted"):
            raise self._not_found(database, collection, doc_id)
        return current

    def _compare_and_replace(self, database, collection, doc_id, current, replacement):
        """Atomically replace iff the stored rev still matches the one we read."""
        updated = self._collection(database, collection).find_one_and_replace(
            {"_id": doc_id, "_rev": current.get("_rev")},
            replacement,
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:  # changed between our read and this write
            raise RevisionConflict(
                "Document was modified concurrently; reload it and retry."
            )
        return self._to_public(updated)

    # -- reads ---------------------------------------------------------------

    def get(self, database: str, collection: str, doc_id: str) -> dict:
        """Return a single live document or raise ``DocumentNotFound``."""
        stored = self._collection(database, collection).find_one({"_id": doc_id})
        if stored is None or stored.get("_deleted"):
            raise self._not_found(database, collection, doc_id)
        return self._to_public(stored)

    def history(self, database: str, collection: str, doc_id: str) -> list[dict]:
        """Return the retained snapshots (oldest first), even for a tombstone."""
        stored = self._collection(database, collection).find_one({"_id": doc_id})
        if stored is None:
            raise self._not_found(database, collection, doc_id)
        return list(stored.get("_history", []))

    def search(
        self,
        database: str,
        collection: str,
        key: str | None = None,
        text: str | None = None,
    ) -> list[dict]:
        """Search a collection by top-level ``key`` and/or contained ``text``.

        - ``key``: only documents that contain that exact key at the top level.
        - ``text``: only documents whose content contains the text (case
          insensitive substring).
        - both: only documents that satisfy both conditions.
        """
        matches = (
            self._to_public(stored)
            for stored in self._query_by_key(database, collection, key)
            if self._matches_text(stored, text)
        )
        return list(matches)

    def _query_by_key(self, database: str, collection: str, key: str | None) -> Iterator[dict]:
        query: dict[str, Any] = {"_deleted": {"$ne": True}}
        if key:
            query[key] = {"$exists": True}
        return self._collection(database, collection).find(query)

    @classmethod
    def _matches_text(cls, stored: dict, text: str | None) -> bool:
        if not text:
            return True
        haystack = json.dumps(cls._body(stored), default=str).lower()
        return text.lower() in haystack

    @staticmethod
    def _not_found(database: str, collection: str, doc_id: str) -> DocumentNotFound:
        return DocumentNotFound(
            f"Document '{doc_id}' not found in '{database}/{collection}'."
        )
