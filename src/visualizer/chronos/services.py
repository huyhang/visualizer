"""Application services (design §6.3) -- thin orchestration.

Each service is injected with the two seams (``StoryStore``, ``EntityGate``) and
does the same shape of work: load, validate purely, persist, present. It knows
nothing about Flask or Mongo internals. Story-logic invariants are *computed*
(reported via presenters), never blocking (all-soft, §8.1); referential rules
are enforced hard here.
"""

from __future__ import annotations

from .book_rules import graph_view, neighborhood
from .calendar import codec_for
from .entity_gate import EntityGate
from .errors import EntityNotFound, EventInUse, InvalidPlotline, TerminusInUse
from .models import Book, Event, Plotline
from .presenters import (
    present_book,
    present_event,
    present_graph,
    present_neighborhood,
    present_plotline,
    present_validate,
)
from .reports import build_report
from .store import StoryStore
from .validation import (
    validate_book_payload,
    validate_event_payload,
    validate_plotline_payload,
)


class _Service:
    """Shared loaders. Subclasses add use-cases per aggregate."""

    def __init__(self, store: StoryStore, entities: EntityGate):
        self.store = store
        self.entities = entities

    # -- loaders (models) ----------------------------------------------------

    def _book(self, book_id: str) -> Book:
        return Book.from_storage(self.store.get_book(book_id))  # raises BookNotFound

    def _plotlines(self, book_id: str) -> list[Plotline]:
        return [Plotline.from_storage(p) for p in self.store.list_plotlines(book_id)]

    def _events_by_id(self, book_id: str) -> dict[str, Event]:
        return {e.id: e for e in (Event.from_storage(e) for e in self.store.list_events(book_id))}

    def _report(self, book: Book):
        events = list(self._events_by_id(book.id).values())
        return build_report(events, self._plotlines(book.id), book.terminus)

    def _require_book(self, book_id: str) -> Book:
        return self._book(book_id)


class BookService(_Service):
    def create(self, book_id, payload, author=None) -> dict:
        book = validate_book_payload(book_id, payload)
        public = self.store.create_book(book_id, book.to_storage(), author=author)
        return present_book(public, self._report(book), plotline_ids=[])

    def get(self, book_id) -> dict:
        book = self._book(book_id)
        public = self.store.get_book(book_id)
        return present_book(public, self._report(book), self._plotline_ids(book_id))

    def update(self, book_id, payload, expected_rev=None, author=None) -> dict:
        self._require_book(book_id)
        book = validate_book_payload(book_id, payload)
        public = self.store.update_book(book_id, book.to_storage(), expected_rev, author)
        return present_book(public, self._report(book), self._plotline_ids(book_id))

    def delete(self, book_id, expected_rev=None, author=None) -> None:
        self._require_book(book_id)
        # Cascade: remove the book's plotlines and events, then the book itself.
        for pl in self.store.list_plotlines(book_id):
            self.store.delete_plotline(book_id, pl["id"], author=author)
        for ev in self.store.list_events(book_id):
            self.store.delete_event(book_id, ev["id"], author=author)
        self.store.delete_book(book_id, expected_rev, author)

    def list(self) -> list[dict]:
        out = []
        for public in self.store.list_books():
            book = Book.from_storage(public)
            out.append(present_book(public, self._report(book), self._plotline_ids(book.id)))
        return out

    def set_terminus(self, book_id, event_id, author=None) -> dict:
        book = self._require_book(book_id)
        self.store.get_event(book_id, event_id)  # raises EventNotFound
        current = self.store.get_book(book_id)
        book.terminus = event_id
        public = self.store.update_book(book_id, book.to_storage(), current["rev"], author)
        return present_book(public, self._report(book), self._plotline_ids(book_id))

    def validate(self, book_id) -> dict:
        book = self._book(book_id)
        return present_validate(self._report(book), codec_for(book))

    def graph(self, book_id) -> dict:
        book = self._book(book_id)
        view = graph_view(self._plotlines(book_id), book.terminus)
        return present_graph(view, self._events_by_id(book_id))

    def _plotline_ids(self, book_id) -> list[str]:
        return [p["id"] for p in self.store.list_plotlines(book_id)]


class EventService(_Service):
    def _check_entities(self, event: Event) -> None:
        missing = self.entities.missing(event.entity_refs())
        if missing:
            raise EntityNotFound(
                "One or more referenced entities do not exist.",
                evidence={"missing": [r.to_dict() for r in missing]},
            )

    def create(self, book_id, event_id, payload, author=None) -> dict:
        self._require_book(book_id)
        event = validate_event_payload(event_id, payload)
        self._check_entities(event)
        public = self.store.create_event(book_id, event_id, event.to_storage(), author=author)
        return present_event(public, codec_for(self._book(book_id)))

    def get(self, book_id, event_id) -> dict:
        public = self.store.get_event(book_id, event_id)
        return present_event(public, codec_for(self._book(book_id)))

    def update(self, book_id, event_id, payload, expected_rev=None, author=None) -> dict:
        self._require_book(book_id)
        event = validate_event_payload(event_id, payload)
        self._check_entities(event)
        public = self.store.update_event(
            book_id, event_id, event.to_storage(), expected_rev, author
        )
        return present_event(public, codec_for(self._book(book_id)))

    def delete(self, book_id, event_id, expected_rev=None, author=None, detach=False) -> None:
        book = self._require_book(book_id)
        self.store.get_event(book_id, event_id)  # raises EventNotFound
        if event_id == book.terminus:
            raise TerminusInUse(
                "Cannot delete the terminus; designate a new terminus first.",
                evidence={"terminus": event_id},
            )
        referencing = [p for p in self.store.list_plotlines(book_id) if event_id in p["events"]]
        if referencing and not detach:
            raise EventInUse(
                "Event is still used by one or more plotlines.",
                evidence={"plotlines": [p["id"] for p in referencing]},
            )
        for p in referencing:  # detach=True
            new_events = [e for e in p["events"] if e != event_id]
            body = {"title": p.get("title"), "events": new_events, "goals": p["goals"]}
            self.store.update_plotline(book_id, p["id"], body, p["rev"], author)
        self.store.delete_event(book_id, event_id, expected_rev, author)

    def neighborhood(self, book_id, event_id, relation=None) -> dict:
        book = self._require_book(book_id)
        events_by_id = self._events_by_id(book_id)
        if event_id not in events_by_id:
            self.store.get_event(book_id, event_id)  # raises EventNotFound
        plotlines = self._plotlines(book_id)
        n = neighborhood(plotlines, event_id, book.terminus)
        full = present_neighborhood(
            n, events_by_id[event_id], events_by_id,
            {p.id: p for p in plotlines}, codec_for(book), book_id,
        )
        if relation == "converging":
            return {"event": full["event"], "converging": full["converging"]}
        if relation == "diverging":
            return {"event": full["event"], "diverging": full["diverging"]}
        if relation == "through":
            return {"event": full["event"], "through": full["through"]}
        return full


class PlotlineService(_Service):
    def _check_event_refs(self, book_id, plotline: Plotline) -> None:
        known = set(self._events_by_id(book_id))
        unknown = [e for e in plotline.events if e not in known]
        if unknown:
            raise InvalidPlotline(
                "Plotline references events that do not exist in this book.",
                evidence={"unknown_events": unknown},
            )

    def _present(self, book, public) -> dict:
        return present_plotline(
            public, book, self._plotlines(book.id), self._events_by_id(book.id),
            codec_for(book),
        )

    def create(self, book_id, plotline_id, payload, author=None) -> dict:
        book = self._require_book(book_id)
        plotline = validate_plotline_payload(plotline_id, payload)
        self._check_event_refs(book_id, plotline)
        public = self.store.create_plotline(book_id, plotline_id, plotline.to_storage(), author)
        return self._present(book, public)

    def get(self, book_id, plotline_id, expand=False) -> dict:
        book = self._book(book_id)
        public = self.store.get_plotline(book_id, plotline_id)
        return present_plotline(
            public, book, self._plotlines(book_id), self._events_by_id(book_id),
            codec_for(book), expand=expand,
        )

    def update(self, book_id, plotline_id, payload, expected_rev=None, author=None) -> dict:
        book = self._require_book(book_id)
        plotline = validate_plotline_payload(plotline_id, payload)
        self._check_event_refs(book_id, plotline)
        public = self.store.update_plotline(
            book_id, plotline_id, plotline.to_storage(), expected_rev, author
        )
        return self._present(book, public)

    def delete(self, book_id, plotline_id, expected_rev=None, author=None) -> None:
        self._require_book(book_id)
        self.store.delete_plotline(book_id, plotline_id, expected_rev, author)
