"""The seams between Logos and the services it reads, in-process and injected.

Logos never invents a book, an event or an article. It reads Chronos to find out
what a book is and which scenes exist, and it reads Akasha to find out whether
the articles its prose mentions are still there. Both are ``Protocol`` seams so a
test hands over a dictionary-backed stand-in and no service-to-service HTTP
exists anywhere in the stack.

The two directions differ on purpose. A Chronos event a section *realises* is a
hard reference: naming one that does not exist is refused, and deleting one that
is named is refused. An Akasha article a paragraph *mentions* is soft: the prose
keeps it and the read reports it as missing, the same posture Chronos takes for a
deleted article and Prithvi takes for a pin.
"""

from typing import Protocol

from visualizer.akasha.errors import AkashaError
from visualizer.chronos.calendar import codec_for
from visualizer.chronos.errors import BookNotFound as ChronosBookNotFound
from visualizer.chronos.models import Book, Event
from visualizer.chronos.presenters import event_when


class ChronosGateway(Protocol):
    def get_book(self, book: str) -> dict | None:
        """The Chronos book, or ``None`` when there is no such book."""

    def list_books(self) -> list[dict]:
        """Every Chronos book, unfiltered. The caller applies its own grants."""

    def missing_events(self, book: str, event_ids: list[str]) -> list[str]:
        """Which of ``event_ids`` are not scenes in this book."""

    def scene_cards(self, book: str, event_ids: list[str]) -> list[dict]:
        """Reader-safe summaries of the named scenes, in the order asked.

        One card per distinct id -- ``{"id", "title", "when", "missing"}`` --
        carrying the scene's display title and its timeframe spelled in the
        book's own calendar, and nothing else Chronos knows. An id with no
        scene behind it comes back *flagged* rather than dropped: a section
        that names a deleted scene should say so, not silently show one card
        fewer than the prose claims.
        """


class ArticleGateway(Protocol):
    def missing_articles(self, refs: list[dict]) -> list[dict]:
        """Which of ``refs`` no longer name a live Akasha article."""


class InProcessChronosGateway:
    def __init__(self, story_store):
        self._stories = story_store

    def get_book(self, book: str) -> dict | None:
        try:
            return self._stories.get_book(book)
        except ChronosBookNotFound:
            return None

    def list_books(self) -> list[dict]:
        return self._stories.list_books()

    def missing_events(self, book: str, event_ids: list[str]) -> list[str]:
        if not event_ids:
            return []
        known = {event["id"] for event in self._stories.list_events(book)}
        return [event for event in event_ids if event not in known]

    def scene_cards(self, book: str, event_ids: list[str]) -> list[dict]:
        wanted = _distinct(event_ids)
        if not wanted:
            return []
        stored = self.get_book(book)
        if stored is None:
            # The book is gone but its prose is still readable, so every scene
            # it named is absent rather than the whole request being an error.
            return [_absent_scene(event_id) for event_id in wanted]
        codec = codec_for(Book.from_storage(stored))
        found = {
            record["id"]: _scene_card(Event.from_storage(record), codec)
            for record in self._stories.get_events(book, wanted)
        }
        return [found.get(event_id) or _absent_scene(event_id) for event_id in wanted]


def _distinct(event_ids: list[str]) -> list[str]:
    """First-seen order: two sections realising one scene ask for it once."""
    return list(dict.fromkeys(event_ids))


def _scene_card(event: Event, codec) -> dict:
    """Only the two Chronos facts the Logos reader has agreed to show."""
    return {
        "id": event.id,
        "title": event.display_title,
        "when": event_when(event, codec),
        "missing": False,
    }


def _absent_scene(event_id: str) -> dict:
    """A scene a section still names but Chronos no longer has."""
    return {"id": event_id, "title": event_id, "when": "", "missing": True}


class InProcessArticleGateway:
    def __init__(self, document_store):
        self._documents = document_store

    def missing_articles(self, refs: list[dict]) -> list[dict]:
        return [ref for ref in refs if not self._exists(ref)]

    def _exists(self, ref: dict) -> bool:
        try:
            self._documents.get(ref["database"], ref["collection"], ref["id"])
        except AkashaError:
            return False
        return True


class LogosReferenceGate:
    """The narrow Logos view Chronos consults before a destructive write."""

    def __init__(self, store):
        self._store = store

    def has_content(self, book: str) -> bool:
        return self._store.has_content(book)

    def sections_referencing(self, book: str, event: str) -> list[dict]:
        return [
            {"volume": row["volume"], "section": row["section"]}
            for row in self._store.sections_referencing(book, event)
        ]


def _fake_scene(event_id: str, title: str | None = None, when: str = "unscheduled"):
    return {"id": event_id, "title": title or event_id, "when": when, "missing": False}


class FakeChronosGateway:
    """A deterministic Chronos stand-in for service and API tests."""

    def __init__(self):
        self._books: dict[str, dict] = {}
        self._events: dict[str, dict[str, dict]] = {}

    def add_book(self, book: str, title: str | None = None, events=()) -> None:
        self._books[book] = {
            "id": book,
            "title": title,
            "overview": "",
            "world": None,
        }
        self._events[book] = {event: _fake_scene(event) for event in events}

    def add_event(
        self, book: str, event: str, title: str | None = None, when: str = "unscheduled"
    ) -> None:
        """Give a scene the title and timeframe the reader will show for it."""
        self._events.setdefault(book, {})[event] = _fake_scene(event, title, when)

    def get_book(self, book: str) -> dict | None:
        return self._books.get(book)

    def list_books(self) -> list[dict]:
        return [self._books[key] for key in sorted(self._books)]

    def missing_events(self, book: str, event_ids: list[str]) -> list[str]:
        known = self._events.get(book, {})
        return [event for event in event_ids if event not in known]

    def scene_cards(self, book: str, event_ids: list[str]) -> list[dict]:
        known = self._events.get(book, {})
        return [
            dict(known[event_id]) if event_id in known else _absent_scene(event_id)
            for event_id in _distinct(event_ids)
        ]


class FakeArticleGateway:
    """An Akasha stand-in holding the refs that currently resolve."""

    def __init__(self, articles=()):
        self._articles = {self._key(ref) for ref in articles}

    def add(self, database: str, collection: str, article: str) -> None:
        self._articles.add((database, collection, article))

    def remove(self, database: str, collection: str, article: str) -> None:
        self._articles.discard((database, collection, article))

    def missing_articles(self, refs: list[dict]) -> list[dict]:
        return [ref for ref in refs if self._key(ref) not in self._articles]

    @staticmethod
    def _key(ref) -> tuple[str, str, str]:
        if isinstance(ref, dict):
            return (ref["database"], ref["collection"], ref["id"])
        return tuple(ref)
