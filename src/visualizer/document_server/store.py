"""Persistence layer for documents.

``DocumentStore`` is the single seam between the application and MongoDB. It
receives its Mongo client via the constructor (inversion of control) so tests
can inject an in-memory client while production injects a real one.

Documents are stored using the caller-supplied ``doc_id`` as the Mongo ``_id``.
On the way out, ``_id`` is renamed to ``id`` so callers never see Mongo
internals.
"""

import json
from typing import Any, Iterator

from pymongo.errors import DuplicateKeyError

from .errors import (
    CollectionAlreadyExists,
    CollectionNotFound,
    DatabaseNotFound,
    DocumentAlreadyExists,
    DocumentNotFound,
)


class DocumentStore:
    def __init__(self, client):
        """:param client: a pymongo-compatible ``MongoClient`` (or mongomock)."""
        self._client = client

    def _collection(self, database: str, collection: str):
        return self._client[database][collection]

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

    @staticmethod
    def _to_public(stored: dict) -> dict:
        """Convert a stored document into the public representation."""
        doc = dict(stored)
        doc_id = doc.pop("_id")
        return {"id": doc_id, "document": doc}

    @staticmethod
    def _to_stored(doc_id: str, document: dict) -> dict:
        """Build the record persisted in Mongo, with ``doc_id`` as ``_id``.

        The URL-supplied id is authoritative, so any ``_id`` inside the payload
        is overwritten.
        """
        stored = dict(document)
        stored["_id"] = doc_id
        return stored

    def create(self, database: str, collection: str, doc_id: str, document: dict) -> dict:
        """Insert a new document.

        The database and collection must already exist (create them via
        ``create_collection``). Fails if the id already exists.
        """
        self._require_namespace(database, collection)
        try:
            self._collection(database, collection).insert_one(
                self._to_stored(doc_id, document)
            )
        except DuplicateKeyError:
            raise DocumentAlreadyExists(
                f"Document '{doc_id}' already exists in '{database}/{collection}'."
            )
        return {"id": doc_id, "document": document}

    def get(self, database: str, collection: str, doc_id: str) -> dict:
        """Return a single document or raise ``DocumentNotFound``."""
        stored = self._collection(database, collection).find_one({"_id": doc_id})
        if stored is None:
            raise self._not_found(database, collection, doc_id)
        return self._to_public(stored)

    def update(self, database: str, collection: str, doc_id: str, document: dict) -> dict:
        """Fully replace an existing document. Fails if it does not exist."""
        result = self._collection(database, collection).replace_one(
            {"_id": doc_id}, self._to_stored(doc_id, document)
        )
        if result.matched_count == 0:
            raise self._not_found(database, collection, doc_id)
        return {"id": doc_id, "document": document}

    def delete(self, database: str, collection: str, doc_id: str) -> None:
        """Delete a document or raise ``DocumentNotFound``."""
        result = self._collection(database, collection).delete_one({"_id": doc_id})
        if result.deleted_count == 0:
            raise self._not_found(database, collection, doc_id)

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
        query = {key: {"$exists": True}} if key else {}
        return self._collection(database, collection).find(query)

    @staticmethod
    def _matches_text(stored: dict, text: str | None) -> bool:
        if not text:
            return True
        content = {k: v for k, v in stored.items() if k != "_id"}
        haystack = json.dumps(content, default=str).lower()
        return text.lower() in haystack

    @staticmethod
    def _not_found(database: str, collection: str, doc_id: str) -> DocumentNotFound:
        return DocumentNotFound(
            f"Document '{doc_id}' not found in '{database}/{collection}'."
        )
