"""Persistence seams for Chronos (design §6.1, §9).

Two boundaries between the app and MongoDB, both built on ``ScopedDocuments``
(which owns the composite key, the ``_rev`` optimistic concurrency and the
author stamp -- see ``documents``):

- ``StoryStore`` -- books, plotlines, events and goals, scoped to a **book**.
- ``CalendarStore`` -- the library of named, reusable calendars, scoped to their
  **owner**.

Both receive their Mongo client and clock by injection (inversion of control) so
tests use an in-memory ``mongomock`` client and a fixed clock. Both are plain
CRUD plus the few targeted queries their callers need; neither holds any domain
rules (those are the pure modules the services call).

Everything lives in a reserved ``_chronos`` database. Deletes are hard (an id
may be recreated); embedded history/activity is a noted future addition.
"""

from collections.abc import Callable
from datetime import datetime

from .documents import ScopedDocuments
from .errors import (
    BookNotFound,
    CalendarNotFound,
    EventNotFound,
    GoalNotFound,
    PlotlineNotFound,
)

CHRONOS_DB = "_chronos"
_BOOKS = "books"
_PLOTLINES = "plotlines"
_EVENTS = "events"
_GOALS = "goals"
_CALENDARS = "calendars"


class StoryStore:
    def __init__(self, client, clock: Callable[[], datetime] | None = None):
        """:param client: a pymongo-compatible client (or mongomock).
        :param clock: returns the current time; injected for deterministic tests.
        """
        self._client = client

        def docs(name):
            return ScopedDocuments(client[CHRONOS_DB][name], "book", clock)

        self._books = docs(_BOOKS)
        self._plotlines = docs(_PLOTLINES)
        self._events = docs(_EVENTS)
        self._goals = docs(_GOALS)

    # -- books ---------------------------------------------------------------
    #
    # A book is its own scope: the document keyed ``"<book>::<book>"``.

    def create_book(self, book_id, body, author=None) -> dict:
        return self._books.insert(book_id, book_id, body, author)

    def get_book(self, book_id) -> dict:
        return self._books.get(book_id, book_id, BookNotFound)

    def update_book(self, book_id, body, expected_rev=None, author=None) -> dict:
        return self._books.replace(book_id, book_id, body, expected_rev, author, BookNotFound)

    def delete_book(self, book_id, expected_rev=None, author=None) -> None:
        self._books.remove(book_id, book_id, expected_rev, author, BookNotFound)

    def check_book_rev(self, book_id, expected_rev=None) -> None:
        """Raise unless the book is still at ``expected_rev``; a no-op when None.

        Lets a caller test the precondition *before* starting work it could not
        undo -- the cascading delete, which has no transaction behind it.
        """
        self._books.check_rev(book_id, book_id, expected_rev, BookNotFound)

    def list_books(self) -> list[dict]:
        return self._books.list_all()

    # -- plotlines -----------------------------------------------------------

    def create_plotline(self, book_id, plotline_id, body, author=None) -> dict:
        return self._plotlines.insert(book_id, plotline_id, body, author)

    def get_plotline(self, book_id, plotline_id) -> dict:
        return self._plotlines.get(book_id, plotline_id, PlotlineNotFound)

    def update_plotline(self, book_id, plotline_id, body, expected_rev=None, author=None) -> dict:
        return self._plotlines.replace(
            book_id, plotline_id, body, expected_rev, author, PlotlineNotFound
        )

    def delete_plotline(self, book_id, plotline_id, expected_rev=None, author=None) -> None:
        self._plotlines.remove(book_id, plotline_id, expected_rev, author, PlotlineNotFound)

    def list_plotlines(self, book_id) -> list[dict]:
        return self._plotlines.list_in_scope(book_id)

    # -- events --------------------------------------------------------------

    def create_event(self, book_id, event_id, body, author=None) -> dict:
        return self._events.insert(book_id, event_id, body, author)

    def get_event(self, book_id, event_id) -> dict:
        return self._events.get(book_id, event_id, EventNotFound)

    def update_event(self, book_id, event_id, body, expected_rev=None, author=None) -> dict:
        return self._events.replace(
            book_id, event_id, body, expected_rev, author, EventNotFound
        )

    def delete_event(self, book_id, event_id, expected_rev=None, author=None) -> None:
        self._events.remove(book_id, event_id, expected_rev, author, EventNotFound)

    def list_events(self, book_id) -> list[dict]:
        return self._events.list_in_scope(book_id)

    # -- goals ---------------------------------------------------------------

    def create_goal(self, book_id, goal_id, body, author=None) -> dict:
        return self._goals.insert(book_id, goal_id, body, author)

    def get_goal(self, book_id, goal_id) -> dict:
        return self._goals.get(book_id, goal_id, GoalNotFound)

    def update_goal(self, book_id, goal_id, body, expected_rev=None, author=None) -> dict:
        return self._goals.replace(book_id, goal_id, body, expected_rev, author, GoalNotFound)

    def delete_goal(self, book_id, goal_id, expected_rev=None, author=None) -> None:
        self._goals.remove(book_id, goal_id, expected_rev, author, GoalNotFound)

    def list_goals(self, book_id) -> list[dict]:
        return self._goals.list_in_scope(book_id)

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


class CalendarStore:
    """The library of named, reusable calendars, scoped to their owner.

    Identity is ``(owner, id)``, which is why this is a separate seam rather
    than another collection on ``StoryStore``: calendar names are generic, so a
    book-style global namespace would let the first writer to register
    "imperial" own that word for everybody, and would tell the next writer that
    a calendar they cannot read exists.

    Nothing here is on the read path of a book's dates. A book attaching a
    calendar **copies** the descriptor, so this store is consulted when browsing
    and attaching, never when formatting.
    """

    def __init__(self, client, clock: Callable[[], datetime] | None = None):
        self._docs = ScopedDocuments(client[CHRONOS_DB][_CALENDARS], "owner", clock)

    def create(self, owner, calendar_id, body, author=None) -> dict:
        return self._docs.insert(owner, calendar_id, body, author or owner)

    def get(self, owner, calendar_id) -> dict:
        return self._docs.get(owner, calendar_id, CalendarNotFound)

    def update(self, owner, calendar_id, body, expected_rev=None, author=None) -> dict:
        return self._docs.replace(
            owner, calendar_id, body, expected_rev, author, CalendarNotFound
        )

    def delete(self, owner, calendar_id, expected_rev=None, author=None) -> None:
        self._docs.remove(owner, calendar_id, expected_rev, author, CalendarNotFound)

    def list_owned_by(self, owner) -> list[dict]:
        return self._docs.list_in_scope(owner)

    def list_all(self) -> list[dict]:
        """Every calendar in the library, unfiltered.

        The route narrows this to what the caller may read -- the same posture as
        ``list_worlds``. This seam has no request identity.
        """
        return self._docs.list_all()
