"""Persistence seam for Chronos (design §6.1, §9).

``StoryStore`` is the single boundary between the app and MongoDB -- the
``DocumentStore`` analogue. It receives its Mongo client and clock by injection
(inversion of control) so tests use an in-memory ``mongomock`` client and a
fixed clock. It is plain CRUD plus two targeted queries the invariants need; it
holds **no** domain rules (those are the pure modules the services call).

Everything lives in a reserved ``_chronos`` database. Books, plotlines and
events are book-scoped: the Mongo ``_id`` is a composite ``"<book>::<id>"`` and
the local ``id``/``book`` are stored as fields. Writes are optimistically
concurrent via ``_rev`` (reused from akasha's pattern) and stamp the
``author``. Deletes are hard (id may be recreated); embedded history/activity is
a noted future addition.
"""

from collections.abc import Callable
from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .errors import (
    AlreadyExists,
    BookNotFound,
    EventNotFound,
    PlotlineNotFound,
    RevisionConflict,
)

CHRONOS_DB = "_chronos"
_BOOKS = "books"
_PLOTLINES = "plotlines"
_EVENTS = "events"

# Fields the store owns; never part of a caller's body.
_INTERNAL = {"_id", "_rev", "_deleted", "book", "id", "created_by", "updated_by", "updated_at"}


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


class StoryStore:
    def __init__(self, client, clock: Callable[[], datetime] | None = None):
        """:param client: a pymongo-compatible client (or mongomock).
        :param clock: returns the current time; injected for deterministic tests.
        """
        self._client = client
        self._clock = clock or _default_clock

    # -- low-level helpers ---------------------------------------------------

    def _coll(self, name: str):
        return self._client[CHRONOS_DB][name]

    @staticmethod
    def _key(book_id: str, local_id: str) -> str:
        return f"{book_id}::{local_id}"

    def _public(self, stored: dict) -> dict:
        body = {k: v for k, v in stored.items() if k not in _INTERNAL}
        return {
            "id": stored["id"],
            "book": stored["book"],
            "rev": stored["_rev"],
            "created_by": stored.get("created_by"),
            "updated_by": stored.get("updated_by"),
            **body,
        }

    def _insert(self, name, book_id, local_id, body, author, not_found_err) -> dict:
        stored = {
            **body,
            "_id": self._key(book_id, local_id),
            "book": book_id,
            "id": local_id,
            "_rev": 1,
            "created_by": author,
            "updated_by": author,
            "updated_at": self._clock().isoformat(),
        }
        try:
            self._coll(name).insert_one(stored)
        except DuplicateKeyError:
            raise AlreadyExists(f"'{local_id}' already exists in book '{book_id}'.")
        return self._public(stored)

    def _find(self, name, book_id, local_id, not_found_err):
        stored = self._coll(name).find_one({"_id": self._key(book_id, local_id)})
        if stored is None:
            raise not_found_err(f"'{local_id}' not found in book '{book_id}'.")
        return stored

    @staticmethod
    def _check_rev(current: dict, expected_rev: int | None) -> None:
        if expected_rev is not None and current["_rev"] != expected_rev:
            raise RevisionConflict(
                f"Modified since revision {expected_rev}; reload and retry.",
                evidence={"expected": expected_rev, "actual": current["_rev"]},
            )

    def _replace(self, name, book_id, local_id, body, expected_rev, author, not_found_err) -> dict:
        current = self._find(name, book_id, local_id, not_found_err)
        self._check_rev(current, expected_rev)
        replacement = {
            **body,
            "_id": current["_id"],
            "book": book_id,
            "id": local_id,
            "_rev": current["_rev"] + 1,
            "created_by": current.get("created_by"),
            "updated_by": author,
            "updated_at": self._clock().isoformat(),
        }
        updated = self._coll(name).find_one_and_replace(
            {"_id": current["_id"], "_rev": current["_rev"]},
            replacement,
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:  # changed between our read and this write
            raise RevisionConflict("Modified concurrently; reload and retry.")
        return self._public(updated)

    def _remove(self, name, book_id, local_id, expected_rev, author, not_found_err) -> None:
        current = self._find(name, book_id, local_id, not_found_err)
        self._check_rev(current, expected_rev)
        result = self._coll(name).delete_one({"_id": current["_id"], "_rev": current["_rev"]})
        if result.deleted_count == 0:
            raise RevisionConflict("Modified concurrently; reload and retry.")

    def _list(self, name, book_id) -> list[dict]:
        cursor = self._coll(name).find({"book": book_id}).sort("id", 1)
        return [self._public(s) for s in cursor]

    # -- books ---------------------------------------------------------------

    def create_book(self, book_id, body, author=None) -> dict:
        return self._insert(_BOOKS, book_id, book_id, body, author, BookNotFound)

    def get_book(self, book_id) -> dict:
        return self._public(self._find(_BOOKS, book_id, book_id, BookNotFound))

    def update_book(self, book_id, body, expected_rev=None, author=None) -> dict:
        return self._replace(_BOOKS, book_id, book_id, body, expected_rev, author, BookNotFound)

    def delete_book(self, book_id, expected_rev=None, author=None) -> None:
        self._remove(_BOOKS, book_id, book_id, expected_rev, author, BookNotFound)

    def list_books(self) -> list[dict]:
        return [self._public(s) for s in self._coll(_BOOKS).find().sort("id", 1)]

    # -- plotlines -----------------------------------------------------------

    def create_plotline(self, book_id, plotline_id, body, author=None) -> dict:
        return self._insert(_PLOTLINES, book_id, plotline_id, body, author, PlotlineNotFound)

    def get_plotline(self, book_id, plotline_id) -> dict:
        return self._public(self._find(_PLOTLINES, book_id, plotline_id, PlotlineNotFound))

    def update_plotline(self, book_id, plotline_id, body, expected_rev=None, author=None) -> dict:
        return self._replace(
            _PLOTLINES, book_id, plotline_id, body, expected_rev, author, PlotlineNotFound
        )

    def delete_plotline(self, book_id, plotline_id, expected_rev=None, author=None) -> None:
        self._remove(_PLOTLINES, book_id, plotline_id, expected_rev, author, PlotlineNotFound)

    def list_plotlines(self, book_id) -> list[dict]:
        return self._list(_PLOTLINES, book_id)

    # -- events --------------------------------------------------------------

    def create_event(self, book_id, event_id, body, author=None) -> dict:
        return self._insert(_EVENTS, book_id, event_id, body, author, EventNotFound)

    def get_event(self, book_id, event_id) -> dict:
        return self._public(self._find(_EVENTS, book_id, event_id, EventNotFound))

    def update_event(self, book_id, event_id, body, expected_rev=None, author=None) -> dict:
        return self._replace(_EVENTS, book_id, event_id, body, expected_rev, author, EventNotFound)

    def delete_event(self, book_id, event_id, expected_rev=None, author=None) -> None:
        self._remove(_EVENTS, book_id, event_id, expected_rev, author, EventNotFound)

    def list_events(self, book_id) -> list[dict]:
        return self._list(_EVENTS, book_id)

    # -- targeted queries the invariants need (design §6.1) ------------------

    def events_involving(self, book_id, character_refs) -> list[dict]:
        """Live events in the book that reference any of these characters (§5.1).

        Filtered in Python -- a book's event set is small -- so the seam stays
        backend-agnostic and easy to fake.
        """
        wanted = {(r["database"], r["collection"], r["id"]) for r in character_refs}
        if not wanted:
            return []
        out = []
        for event in self.list_events(book_id):
            chars = {(c["database"], c["collection"], c["id"]) for c in event.get("characters", [])}
            if chars & wanted:
                out.append(event)
        return out

    def get_events(self, book_id, event_ids) -> list[dict]:
        """Fetch events by id, returned in the requested order (missing skipped)."""
        by_id = {e["id"]: e for e in self.list_events(book_id)}
        return [by_id[eid] for eid in event_ids if eid in by_id]
