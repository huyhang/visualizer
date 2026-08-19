"""Application services (design §6.3) -- thin orchestration.

Each service is injected with the two seams (``StoryStore``, ``EntityGate``) and
does the same shape of work: load, validate purely, persist, present. It knows
nothing about Flask or Mongo internals. Story-logic invariants are *computed*
(reported via presenters), never blocking (all-soft, §8.1); referential rules
are enforced hard here.
"""

from __future__ import annotations

from dataclasses import replace

from .book_health import book_issues
from .book_rules import graph_view, neighborhood
from .browsing import (
    DEFAULT_PER_PAGE,
    browse_events,
    browse_plotlines,
    dominant_database,
)
from .calendar import codec_for, codec_for_attachment
from .continuation import effective_paths, resolve, resolve_all, would_cycle
from .entity_gate import EntityGate
from .errors import (
    EntityNotFound,
    EventInUse,
    GoalCycle,
    GoalInUse,
    InvalidGoal,
    InvalidPlotline,
    PlotlineCycle,
    PlotlineInUse,
    TerminusInUse,
)
from .goal_rules import dependency_cycle
from .models import Book, EntityRef, Event, Goal, Plotline
from .plotline_health import conflict_counts
from .presenters import (
    as_preview,
    event_when,
    goal_ref,
    goal_view,
    present_book,
    present_book_report,
    present_calendar,
    present_dates,
    present_event,
    present_goal,
    present_graph,
    present_neighborhood,
    present_plotline,
    present_ticks,
    present_validate,
)
from .reports import build_report
from .scheduling import window_for
from .store import CalendarStore, StoryStore
from .validation import (
    validate_book_payload,
    validate_calendar_payload,
    validate_event_payload,
    validate_goal_payload,
    validate_plotline_payload,
    validate_timeframe_payload,
)

# A stand-in used only while previewing a plotline that has no id yet. It never
# reaches the store -- a preview writes nothing.
DRAFT_PLOTLINE_ID = "(new plotline)"


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

    def _goals(self, book_id: str) -> list[Goal]:
        return [Goal.from_storage(g) for g in self.store.list_goals(book_id)]

    def _events_by_id(self, book_id: str) -> dict[str, Event]:
        return {e.id: e for e in (Event.from_storage(e) for e in self.store.list_events(book_id))}

    def _report(self, book: Book):
        events = list(self._events_by_id(book.id).values())
        return build_report(
            events, self._plotlines(book.id), book.terminus,
            missing_refs=self._missing_refs(events),
            goals=self._goals(book.id),
        )

    def _missing_refs(self, events) -> list:
        """Akasha articles this book's scenes point at that are no longer there.

        Writes already refuse an unknown reference, so anything here was deleted
        after the scene naming it was written. Asked once for the whole book and
        de-duplicated by the gate, so a cast of twenty across sixty scenes costs
        twenty lookups rather than sixty -- each a keyed read, and the same seam
        every write already goes through.
        """
        return self.entities.missing(
            ref for event in events for ref in event.entity_refs()
        )

    def _require_book(self, book_id: str) -> Book:
        return self._book(book_id)

    def _check_event_refs(self, book_id: str, plotline: Plotline) -> None:
        """Referential, so hard (§8.1): a thread cannot list a scene that is not
        in the book. Shared by the writers and by the editor's preview, so a
        draft is judged by exactly the rule its save will face."""
        known = set(self._events_by_id(book_id))
        unknown = [e for e in plotline.events if e not in known]
        if unknown:
            raise InvalidPlotline(
                "Plotline references events that do not exist in this book.",
                evidence={"unknown_events": unknown},
            )

    def _check_goal_refs(self, book_id: str, plotline: Plotline) -> None:
        """A thread may only serve goals this book has (§3.5).

        The same class of rule as the scene references above, and refused for
        the same reason: a goal id that names nothing is not a story problem to
        report but a pointer to nowhere. Serving *no* goals is fine -- that one
        is reported (``GOAL_UNSERVED``), because a thread without a purpose yet
        is a draft, not a mistake.
        """
        known = {g.id for g in self._goals(book_id)}
        unknown = [g for g in plotline.goals if g not in known]
        if unknown:
            raise InvalidPlotline(
                "Plotline serves goals that do not exist in this book.",
                evidence={"unknown_goals": unknown},
            )


class BookService(_Service):
    """Books, and the calendars they take from the library.

    The library is where calendars are authored; a book *chooses* one. So the
    descriptor a book stores is never supplied by the caller -- it is read out
    of the library here, at the write, and copied in. Three things follow that
    would each need their own guard otherwise: a book can only ever hold a
    calendar that really exists in somebody's library; the copy always agrees
    with the entry it names at the revision it names; and provenance cannot be
    forged, because it is the *only* thing the caller gets to state.
    """

    def __init__(self, store: StoryStore, entities: EntityGate, calendars: CalendarStore):
        super().__init__(store, entities)
        self.calendars = calendars

    def _resolve_attachments(self, book: Book, held: Book | None = None) -> Book:
        """Fill each attachment's descriptor from the library entry it names.

        Copying happens **on attach, not on every save**. If it happened on
        every save, editing a book's title would quietly adopt whatever the
        library had become since -- re-dating a finished story through the one
        door every writer uses, which is the whole thing copying exists to stop.

        So ``source.rev`` is how a caller says which of the two it wants:

        - **omitted** -- "give me this calendar as it stands". A fresh attach,
          or the writer explicitly taking an update.
        - **present** -- "I already hold revision N; keep it". Honoured when the
          book really does hold that attachment at that revision; otherwise
          there is nothing to keep and the current entry is read instead.

        The pre-library single-``calendar`` spelling has no source and is left
        alone: those books are migrated deliberately, not on their next save.
        """
        keepable = {
            (a.id, a.source["owner"], a.source["calendar"]): a
            for a in (held.calendars if held else [])
            if a.source
        }
        for attachment in book.calendars:
            if attachment.source is None:
                continue
            owner, name = attachment.source["owner"], attachment.source["calendar"]
            wanted = attachment.source.get("rev")
            already = keepable.get((attachment.id, owner, name))
            if wanted is not None and already and already.source.get("rev") == wanted:
                attachment.descriptor = already.descriptor
                attachment.source = dict(already.source)
                continue
            entry = self.calendars.get(owner, name)  # raises CalendarNotFound
            attachment.descriptor = entry["descriptor"]
            # The revision actually read, never the one the caller claimed --
            # which is what makes "the library has moved on" a fact rather than
            # a guess, and why the copy needs no checksum stored beside it.
            attachment.source = {"owner": owner, "calendar": name, "rev": entry["rev"]}
        return book

    def create(self, book_id, payload, author=None) -> dict:
        book = self._resolve_attachments(validate_book_payload(book_id, payload))
        public = self.store.create_book(book_id, book.to_storage(), author=author)
        return present_book(public, self._report(book), plotline_ids=[])

    def get(self, book_id) -> dict:
        book = self._book(book_id)
        public = self.store.get_book(book_id)
        return present_book(public, self._report(book), self._plotline_ids(book_id))

    def update(self, book_id, payload, expected_rev=None, author=None) -> dict:
        held = self._require_book(book_id)
        book = self._resolve_attachments(validate_book_payload(book_id, payload), held)
        public = self.store.update_book(book_id, book.to_storage(), expected_rev, author)
        return present_book(public, self._report(book), self._plotline_ids(book_id))

    def delete(self, book_id, expected_rev=None, author=None) -> None:
        self._require_book(book_id)
        # Check the caller's precondition *first*. The cascade below is a run of
        # single-document deletes with no transaction behind it, so a stale
        # If-Match discovered at the last step would leave the book stripped of
        # its story but still present -- a state nobody asked for, and one no
        # error message can undo.
        self.store.check_book_rev(book_id, expected_rev)
        # Cascade: remove everything the book holds, then the book itself.
        for pl in self.store.list_plotlines(book_id):
            self.store.delete_plotline(book_id, pl["id"], author=author)
        for ev in self.store.list_events(book_id):
            self.store.delete_event(book_id, ev["id"], author=author)
        for goal in self.store.list_goals(book_id):
            self.store.delete_goal(book_id, goal["id"], author=author)
        # Re-checked here, not merely trusted from above: nothing stops another
        # writer touching the book while the cascade runs.
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

    def validate(self, book_id, calendar_id=None) -> dict:
        book = self._book(book_id)
        return present_validate(self._report(book), codec_for(book, calendar_id))

    def graph(self, book_id, calendar_id=None) -> dict:
        book = self._book(book_id)
        plotlines = self._plotlines(book_id)
        view = graph_view(effective_paths(plotlines), book.terminus)
        return present_graph(
            view, self._events_by_id(book_id),
            {p.id: p for p in plotlines}, codec_for(book, calendar_id),
            self._goals(book_id),
        )

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

    def create(self, book_id, event_id, payload, author=None, calendar_id=None) -> dict:
        """Write a scene. ``calendar_id`` is which reckoning the body's dates are
        written in -- the same selector reads use, so a writer schedules in
        whichever calendar they are looking at, and reads the result back in it."""
        book = self._require_book(book_id)
        codec = codec_for(book, calendar_id)
        event = validate_event_payload(event_id, payload, codec)
        self._check_entities(event)
        public = self.store.create_event(book_id, event_id, event.to_storage(), author=author)
        return present_event(public, codec)

    def get(self, book_id, event_id, calendar_id=None) -> dict:
        public = self.store.get_event(book_id, event_id)
        book = self._book(book_id)
        return present_event(
            public, codec_for(book, calendar_id), self._window(book_id, event_id)
        )

    def _window(self, book_id, event_id):
        """Where this scene could go, from its plotline neighbours (§4.2)."""
        events = self._events_by_id(book_id)
        if events.get(event_id) is not None and events[event_id].is_scheduled:
            return None
        return window_for(event_id, effective_paths(self._plotlines(book_id)), events)

    def update(self, book_id, event_id, payload, expected_rev=None, author=None,
               calendar_id=None) -> dict:
        book = self._require_book(book_id)
        codec = codec_for(book, calendar_id)
        event = validate_event_payload(event_id, payload, codec)
        self._check_entities(event)
        public = self.store.update_event(
            book_id, event_id, event.to_storage(), expected_rev, author
        )
        return present_event(public, codec)

    def delete(self, book_id, event_id, expected_rev=None, author=None, detach=False) -> None:
        book = self._require_book(book_id)
        self.store.get_event(book_id, event_id)  # raises EventNotFound
        if event_id == book.terminus:
            raise TerminusInUse(
                "Cannot delete the terminus; designate a new terminus first.",
                evidence={"terminus": event_id},
            )
        referencing = [p for p in self.store.list_plotlines(book_id) if event_id in p["events"]]
        # A goal that lands on this scene is holding it just as a thread listing
        # it is: delete the scene and the goal is achieved nowhere, which the
        # writer would find out from the report rather than from the delete.
        achieving = [g for g in self._goals(book_id) if g.achieved_at == event_id]
        if (referencing or achieving) and not detach:
            raise EventInUse(
                _event_in_use_message(referencing, achieving),
                evidence={
                    "plotlines": [p["id"] for p in referencing],
                    **({"goals": [g.id for g in achieving]} if achieving else {}),
                },
            )
        for goal in achieving:  # detach=True
            stored = self.store.get_goal(book_id, goal.id)
            self.store.update_goal(
                book_id, goal.id,
                replace(goal, achieved_at=None).to_storage(), stored["rev"], author,
            )
        for p in referencing:  # detach=True
            # Round-trip the *model* rather than re-listing the stored fields.
            # An enumerated body is how a field added later gets dropped in
            # silence: nothing recomputes it and no verdict mentions it, so the
            # loss surfaces months later as prose the writer swears they wrote.
            # ``replace`` copies every field this one does not name, so the only
            # way to lose one is to delete it from the model itself.
            thread = Plotline.from_storage(p)
            detached = replace(thread, events=[e for e in thread.events if e != event_id])
            self.store.update_plotline(
                book_id, p["id"], detached.to_storage(), p["rev"], author
            )
        self.store.delete_event(book_id, event_id, expected_rev, author)

    def neighborhood(self, book_id, event_id, relation=None, calendar_id=None) -> dict:
        book = self._require_book(book_id)
        events_by_id = self._events_by_id(book_id)
        if event_id not in events_by_id:
            self.store.get_event(book_id, event_id)  # raises EventNotFound
        plotlines = self._plotlines(book_id)
        n = neighborhood(effective_paths(plotlines), event_id, book.terminus)
        full = present_neighborhood(
            n, events_by_id[event_id], events_by_id,
            {p.id: p for p in plotlines}, codec_for(book, calendar_id), book_id,
        )
        if relation == "converging":
            return {"event": full["event"], "converging": full["converging"]}
        if relation == "diverging":
            return {"event": full["event"], "diverging": full["diverging"]}
        if relation == "through":
            return {"event": full["event"], "through": full["through"]}
        return full


def _event_in_use_message(plotlines: list, goals: list) -> str:
    """Why a scene cannot be deleted, naming whichever holds it.

    Two holders, so three sentences rather than one that hedges: a writer told
    "something still uses this" has to go and find out what.
    """
    if plotlines and goals:
        return "Event is still used by one or more plotlines, and achieves a goal."
    if goals:
        return "Event is where one or more goals are achieved."
    return "Event is still used by one or more plotlines."


class PlotlineService(_Service):
    def _check_continuation(self, book_id, plotline: Plotline) -> None:
        """Referential + structural checks on ``continues_into`` -- both hard.

        An unresolvable chain has no effective path, so unlike a story-logic
        finding it cannot be reported and left in place.
        """
        if plotline.continues_into is None:
            return
        siblings = self._plotlines(book_id)
        if plotline.continues_into not in {p.id for p in siblings}:
            raise InvalidPlotline(
                f"Continues into '{plotline.continues_into}', which does not exist "
                "in this book.",
                evidence={"continues_into": plotline.continues_into},
            )
        cycle = would_cycle(plotline, siblings)
        if cycle:
            raise PlotlineCycle(
                "This continuation would make the plotline chain loop.",
                evidence={"cycle": cycle},
            )
        self._check_join_point(plotline, siblings)

    def _check_join_point(self, plotline: Plotline, siblings: list[Plotline]) -> None:
        """``continues_into_at`` must name a scene on the target's resolved path.

        Hard, for the same reason the other two are: a join point that matches
        nothing leaves the thread with no path to be judged on. Checked against
        the *resolved* target, so joining at a scene the trunk itself inherits
        is allowed -- what the writer sees on that thread is what they may pick.
        """
        if plotline.continues_into_at is None:
            return
        target = resolve(plotline.continues_into, {p.id: p for p in siblings})
        if plotline.continues_into_at not in target.events:
            raise InvalidPlotline(
                f"Joins '{plotline.continues_into}' at '{plotline.continues_into_at}', "
                "which is not a scene on that thread.",
                evidence={
                    "continues_into": plotline.continues_into,
                    "continues_into_at": plotline.continues_into_at,
                },
            )

    def _present(self, book, public, calendar_id=None) -> dict:
        events_by_id = self._events_by_id(book.id)
        return present_plotline(
            public, book, self._plotlines(book.id), events_by_id,
            codec_for(book, calendar_id),
            missing_refs=self._missing_refs(events_by_id.values()),
            goals=self._goals(book.id),
        )

    def create(self, book_id, plotline_id, payload, author=None) -> dict:
        book = self._require_book(book_id)
        plotline = validate_plotline_payload(plotline_id, payload)
        self._check_event_refs(book_id, plotline)
        self._check_goal_refs(book_id, plotline)
        self._check_continuation(book_id, plotline)
        public = self.store.create_plotline(book_id, plotline_id, plotline.to_storage(), author)
        return self._present(book, public)

    def get(self, book_id, plotline_id, expand=False, calendar_id=None) -> dict:
        book = self._book(book_id)
        public = self.store.get_plotline(book_id, plotline_id)
        events_by_id = self._events_by_id(book_id)
        return present_plotline(
            public, book, self._plotlines(book_id), events_by_id,
            codec_for(book, calendar_id), expand=expand,
            missing_refs=self._missing_refs(events_by_id.values()),
            goals=self._goals(book_id),
        )

    def update(self, book_id, plotline_id, payload, expected_rev=None, author=None) -> dict:
        book = self._require_book(book_id)
        plotline = validate_plotline_payload(plotline_id, payload)
        self._check_event_refs(book_id, plotline)
        self._check_goal_refs(book_id, plotline)
        self._check_continuation(book_id, plotline)
        public = self.store.update_plotline(
            book_id, plotline_id, plotline.to_storage(), expected_rev, author
        )
        return self._present(book, public)

    def inline(self, book_id, plotline_id, expected_rev=None, author=None) -> dict:
        """Absorb the continuation chain into this plotline's own segment.

        The inverse of adopting a continuation: the thread keeps the exact story
        it had, but stops depending on another plotline. A no-op (and so safely
        repeatable) when there is no continuation to absorb.
        """
        book = self._require_book(book_id)
        public = self.store.get_plotline(book_id, plotline_id)
        plotline = Plotline.from_storage(public)
        if plotline.continues_into is None:
            return self._present(book, public)

        resolution = resolve(plotline_id, {p.id: p for p in self._plotlines(book_id)})
        # Refuse on a broken chain rather than silently inlining a partial path.
        if resolution.cycle:
            raise PlotlineCycle(
                "Cannot inline: the continuation chain loops.",
                evidence={"cycle": resolution.cycle},
            )
        if resolution.missing:
            raise InvalidPlotline(
                f"Cannot inline: continues into '{resolution.missing}', which does "
                "not exist.",
                evidence={"missing": resolution.missing},
            )
        if resolution.anchor_missing:
            raise InvalidPlotline(
                f"Cannot inline: joins at '{resolution.anchor_missing}', which is no "
                "longer on the continuation's path.",
                evidence={"anchor_missing": resolution.anchor_missing},
            )
        # Same rule as the detach rewrite above: change the fields this operation
        # is *about* and carry the rest across untouched. Inlining is defined as
        # a change of representation, not of content -- a thread must come out of
        # it saying exactly what it said going in, which is why the join point
        # goes with the target it qualified.
        inlined = replace(
            plotline, events=resolution.events, continues_into=None, continues_into_at=None
        )
        updated = self.store.update_plotline(
            book_id, plotline_id, inlined.to_storage(), expected_rev, author
        )
        return self._present(book, updated)

    def delete(
        self, book_id, plotline_id, expected_rev=None, author=None, inline_dependents=False
    ) -> None:
        """Delete a plotline, refusing to orphan threads that continue into it.

        Referential integrity is hard (§8.1): a dangling ``continues_into`` has
        no effective path. ``inline_dependents`` absorbs this plotline into each
        dependent first, so their stories survive the deletion intact.
        """
        self._require_book(book_id)
        self.store.get_plotline(book_id, plotline_id)  # raises PlotlineNotFound
        dependents = [
            p for p in self._plotlines(book_id) if p.continues_into == plotline_id
        ]
        if dependents and not inline_dependents:
            raise PlotlineInUse(
                "Other plotlines continue into this one.",
                evidence={"plotlines": sorted(p.id for p in dependents)},
            )
        for dependent in dependents:
            self.inline(book_id, dependent.id, author=author)
        self.store.delete_plotline(book_id, plotline_id, expected_rev, author)


class GoalService(_Service):
    """Goals: what the book is trying to bring about (design §3.5).

    Three things are refused here, and everything else about a goal is reported
    instead. The three are the ones that would leave a record describing
    nothing: a dependency on a goal this book does not have, a chain of
    dependencies that loops, and an achieving scene that is not in the book.
    Whether the story *delivers* a goal -- on time, on a thread that pursues it,
    at all -- is story logic, so it is computed on every read (``goal_rules``)
    and never blocks a write (§8.1).
    """

    def _view(self, book, calendar_id=None):
        return goal_view(
            self._goals(book.id), self._plotlines(book.id),
            self._events_by_id(book.id), codec_for(book, calendar_id),
        )

    def _check_dependencies(self, book_id: str, goal: Goal) -> None:
        siblings = [g for g in self._goals(book_id) if g.id != goal.id]
        known = {g.id for g in siblings}
        unknown = [d for d in goal.depends_on if d not in known]
        if unknown:
            raise InvalidGoal(
                "This goal depends on goals that do not exist in this book.",
                evidence={"unknown_goals": unknown},
            )
        cycle = dependency_cycle(goal, siblings)
        if cycle:
            raise GoalCycle(
                "These dependencies would make a chain of goals loop.",
                evidence={"cycle": cycle},
            )

    def _check_achieved_at(self, book_id: str, goal: Goal) -> None:
        if goal.achieved_at is None:
            return
        if goal.achieved_at not in self._events_by_id(book_id):
            raise InvalidGoal(
                f"Achieved at '{goal.achieved_at}', which is not a scene in this book.",
                evidence={"achieved_at": goal.achieved_at},
            )

    def create(self, book_id, goal_id, payload, author=None, calendar_id=None) -> dict:
        book = self._require_book(book_id)
        goal = validate_goal_payload(goal_id, payload)
        self._check_dependencies(book_id, goal)
        self._check_achieved_at(book_id, goal)
        public = self.store.create_goal(book_id, goal_id, goal.to_storage(), author)
        return present_goal(public, self._view(book, calendar_id))

    def get(self, book_id, goal_id, calendar_id=None) -> dict:
        book = self._book(book_id)
        public = self.store.get_goal(book_id, goal_id)
        return present_goal(public, self._view(book, calendar_id))

    def update(self, book_id, goal_id, payload, expected_rev=None, author=None,
               calendar_id=None) -> dict:
        book = self._require_book(book_id)
        goal = validate_goal_payload(goal_id, payload)
        self._check_dependencies(book_id, goal)
        self._check_achieved_at(book_id, goal)
        public = self.store.update_goal(
            book_id, goal_id, goal.to_storage(), expected_rev, author
        )
        return present_goal(public, self._view(book, calendar_id))

    def list(self, book_id, calendar_id=None) -> list[dict]:
        """Every goal in the book, each read against all the others.

        Unpaginated, unlike the scene library: a book has goals in the tens, and
        the dependency diagram needs the whole graph in one piece -- a page of
        it would draw edges to goals that are not there.
        """
        book = self._book(book_id)
        view = self._view(book, calendar_id)
        return [present_goal(g, view) for g in self.store.list_goals(book_id)]

    def delete(self, book_id, goal_id, expected_rev=None, author=None, detach=False) -> None:
        """Delete a goal, refusing to strand what points at it.

        Threads serve goals and goals rest on goals, and both are ids stored
        elsewhere -- so deleting one without a word would leave a thread saying
        it pursues something that no longer exists. Refused by default and named
        in the evidence; ``detach`` unpicks those references first, which is the
        same bargain ``EVENT_IN_USE`` offers.
        """
        self._require_book(book_id)
        self.store.get_goal(book_id, goal_id)  # raises GoalNotFound
        serving = [p for p in self._plotlines(book_id) if goal_id in p.goals]
        dependents = [g for g in self._goals(book_id) if goal_id in g.depends_on]
        if (serving or dependents) and not detach:
            raise GoalInUse(
                "Threads serve this goal, or other goals depend on it.",
                evidence={
                    "plotlines": sorted(p.id for p in serving),
                    "goals": sorted(g.id for g in dependents),
                },
            )
        for plotline in serving:
            self._rewrite_plotline(book_id, plotline, goal_id, author)
        for dependent in dependents:
            self._rewrite_goal(book_id, dependent, goal_id, author)
        self.store.delete_goal(book_id, goal_id, expected_rev, author)

    def _rewrite_plotline(self, book_id, plotline: Plotline, goal_id: str, author) -> None:
        """Drop one goal from a thread, carrying every other field across.

        ``replace`` rather than an enumerated body, for the reason the scene
        detach gives: a field added later that nobody remembered to list here
        would be dropped in silence.
        """
        stored = self.store.get_plotline(book_id, plotline.id)
        detached = replace(plotline, goals=[g for g in plotline.goals if g != goal_id])
        self.store.update_plotline(
            book_id, plotline.id, detached.to_storage(), stored["rev"], author
        )

    def _rewrite_goal(self, book_id, goal: Goal, dependency_id: str, author) -> None:
        stored = self.store.get_goal(book_id, goal.id)
        detached = replace(
            goal, depends_on=[d for d in goal.depends_on if d != dependency_id]
        )
        self.store.update_goal(
            book_id, goal.id, detached.to_storage(), stored["rev"], author
        )


class CalendarService:
    """The library of named, reusable calendars (design §4.1).

    Deliberately not a ``_Service``: a library calendar hangs off its owner, not
    off a book, and touches neither the story store nor Akasha. It is also
    entirely off the read path of a book's dates -- attaching one *copies* the
    descriptor into the book, so nothing here is consulted when formatting a
    tick. That is what keeps ``codec_for`` pure and ``GET /books`` from becoming
    one query per book.
    """

    def __init__(self, calendars: CalendarStore):
        self.calendars = calendars

    def create(self, owner, calendar_id, payload, author=None) -> dict:
        calendar = validate_calendar_payload(calendar_id, payload)
        public = self.calendars.create(owner, calendar_id, calendar.to_storage(), author)
        return present_calendar(public)

    def get(self, owner, calendar_id) -> dict:
        return present_calendar(self.calendars.get(owner, calendar_id))

    def update(self, owner, calendar_id, payload, expected_rev=None, author=None) -> dict:
        self.calendars.get(owner, calendar_id)  # raises CalendarNotFound
        calendar = validate_calendar_payload(calendar_id, payload)
        public = self.calendars.update(
            owner, calendar_id, calendar.to_storage(), expected_rev, author
        )
        return present_calendar(public)

    def delete(self, owner, calendar_id, expected_rev=None, author=None) -> None:
        """Remove a library entry. Books that copied it are untouched.

        Deliberately not a cascade: the copies *are* those books' calendars, and
        deleting a shared record out from under someone else's story is exactly
        what copying was chosen to prevent. Their provenance goes dangling, which
        a reader reports the way it reports a deleted Akasha article.
        """
        self.calendars.delete(owner, calendar_id, expected_rev, author)

    def library(self) -> list[dict]:
        """Every calendar there is, unfiltered -- the route narrows it to what
        the caller may read, the same posture as ``list_worlds``."""
        return [present_calendar(c) for c in self.calendars.list_all()]


class VisualizerService(_Service):
    """Orchestration behind the plotline visualiser and its editor.

    The use-cases the SPA needs and the JSON API does not already offer: ordered,
    filtered, paginated tables of a book's plotlines and scenes; a same-origin
    proxy for the Akasha articles those scenes reference (so the browser never
    talks cross-service); and a **preview**, which answers "what would this
    thread look like if I saved it?" without writing anything.

    All the interesting logic is in the pure modules (``browsing``,
    ``plotline_health``) and the ``EntityGate`` seam; this just loads and hands
    off. Writes still go through the plotline/event services -- nothing here
    persists.
    """

    def browse_plotlines(
        self, book_id, query: str = "", page: int = 1, per_page: int = DEFAULT_PER_PAGE,
        calendar_id=None,
    ) -> dict:
        # The table labels one thing -- when each goal chip lands -- so it reads
        # through the chosen calendar like every other book-scoped view, and a
        # stale ``?calendar=`` 404s here the way it does everywhere else.
        book = self._require_book(book_id)
        codec = codec_for(book, calendar_id)  # 404 for an unattached calendar
        events_by_id = self._events_by_id(book_id)
        plotlines = self._plotlines(book_id)
        # Filter on the *resolved* path so a word from a shared/continued scene
        # still surfaces the thread -- the same path the plotline view shows.
        paths = effective_paths(plotlines)
        # Counted for the whole book at once, not once per thread.
        counts = conflict_counts(
            paths, events_by_id, self._missing_refs(events_by_id.values())
        )
        goals_by_id = {g.id: g for g in self._goals(book_id)}
        rows = [
            self._row(pl, paths, events_by_id, book_id, counts, goals_by_id, codec)
            for pl in plotlines
        ]
        return browse_plotlines(rows, query=query, page=page, per_page=per_page)

    @staticmethod
    def _row(pl: Plotline, paths, events_by_id, book_id, counts, goals_by_id, codec) -> dict:
        path = paths.get(pl.id, list(pl.events))
        titles = [events_by_id[eid].display_title for eid in path if eid in events_by_id]
        return {
            "id": pl.id,
            "book": book_id,
            "name": pl.display_title,
            "overview": pl.overview,
            # Named, not just listed: the table draws a chip per goal and links
            # it, and the filter matches what the writer can see -- the title --
            # rather than the slug it is stored under. The same reference shape
            # every other response uses, so a client has one thing to render.
            "goals": [
                goal_ref(gid, goals_by_id, events_by_id, codec) for gid in pl.goals
            ],
            "event_titles": titles,
            "conflicts": counts.get(pl.id, 0),
        }

    # -- scenes ---------------------------------------------------------------

    def browse_events(
        self, book_id, query: str = "", page: int = 1, per_page: int = DEFAULT_PER_PAGE,
        calendar_id=None,
    ) -> dict:
        """The book's scenes in story order -- what the editor picks from."""
        book = self._require_book(book_id)
        codec = codec_for(book, calendar_id)
        paths = effective_paths(self._plotlines(book_id))
        rows = [
            self._event_row(event, codec, paths, book_id)
            for event in self._events_by_id(book_id).values()
        ]
        return browse_events(rows, query=query, page=page, per_page=per_page)

    @staticmethod
    def _event_row(event: Event, codec, paths, book_id) -> dict:
        return {
            "id": event.id,
            "book": book_id,
            "name": event.display_title,
            "when": event_when(event, codec),
            "scheduled": event.is_scheduled,
            "start_tick": event.start_tick,
            "end_tick": event.end_tick,
            "location": event.location.id,
            # The whole reference as well as the id. Chronos does not know what
            # Akasha calls this place -- only the browser can ask, and it does
            # so lazily and memoised (``entities.js``), the same way the event
            # cards do. Without the database and collection it cannot ask at
            # all, and a table of slugs is the result.
            "location_ref": event.location.to_dict(),
            # Findable by where it happens and who is in it, not just its title.
            "keywords": [ref.id for ref in event.entity_refs()],
            "plotlines": sorted(pid for pid, path in paths.items() if event.id in path),
        }

    # -- the book's continuity report ------------------------------------------

    def book_report(self, book_id, calendar_id=None) -> dict:
        """Everything wrong across every thread in one book (``book_health``).

        The per-thread views answer "what is wrong *here*"; this answers the
        question a writer with six threads has instead, and which nothing in the
        browser could reach before. Resolutions are loaded once and passed whole,
        so the paths the rules run on and the reason a chain is broken are read
        from the same data.
        """
        book = self._require_book(book_id)
        plotlines = self._plotlines(book_id)
        events_by_id = self._events_by_id(book_id)
        goals = self._goals(book_id)
        issues = book_issues(
            resolve_all(plotlines),
            events_by_id,
            codec_for(book, calendar_id),
            missing_refs=self._missing_refs(events_by_id.values()),
            terminus=book.terminus,
            goals=goals,
            plotlines=plotlines,
        )
        return present_book_report(issues, events_by_id, plotlines, goals)

    # -- preview --------------------------------------------------------------

    def preview_plotline(self, book_id, payload, calendar_id=None) -> dict:
        """Present a *candidate* thread exactly as saving it would present it.

        The editor calls this after every reorder, so the writer sees a fix (or a
        break) land as they drag. It runs the candidate through the same
        presenter as a stored plotline, which is the point: live feedback and the
        saved result cannot drift apart, and no rule has to be reimplemented in
        the browser.

        Nothing is written, and no id needs to exist yet -- a plotline being
        drafted previews the same way one being edited does.
        """
        book = self._require_book(book_id)
        body = dict(payload or {})
        plotline_id = body.get("id") or DRAFT_PLOTLINE_ID
        candidate = validate_plotline_payload(plotline_id, body)
        self._check_event_refs(book_id, candidate)
        self._check_goal_refs(book_id, candidate)
        public = {
            **candidate.to_storage(), "id": plotline_id, "book": book_id, "rev": 0,
        }
        events_by_id = self._events_by_id(book_id)
        presented = present_plotline(
            public, book, self._plotlines(book_id), events_by_id,
            codec_for(book, calendar_id), expand=True,
            missing_refs=self._missing_refs(events_by_id.values()),
            goals=self._goals(book_id),
        )
        return as_preview(presented, book_id)

    # -- the calendar ----------------------------------------------------------

    def format_ticks(self, book_id, ticks: list[int], calendar_id=None) -> dict:
        """What this book's calendars call these ticks (see ``present_ticks``).

        Every attached reckoning answers, not just the one being viewed through:
        a writer placing a scene wants to see it dated in each of them at once,
        and the codecs are pure, so the extra readings cost no I/O.
        """
        book = self._require_book(book_id)
        return present_ticks(ticks, codec_for(book, calendar_id), self._readings(book))

    def resolve_dates(self, book_id, payload, calendar_id=None) -> dict:
        """Which ticks a pair of calendar dates names (see ``present_dates``).

        The write-side twin of ``format_ticks``: the scene form asks this while
        the writer types, so what it echoes is the server's own arithmetic
        rather than a second implementation of the odometer in JavaScript.
        Judges nothing and stores nothing -- an impossible date is the only way
        it fails.
        """
        book = self._require_book(book_id)
        codec = codec_for(book, calendar_id)
        start, end = validate_timeframe_payload(payload, codec)
        return present_dates(start, end, codec, self._readings(book))

    def _readings(self, book) -> list:
        """Every attached reckoning, ready to date the same tick. Pure, so the
        extra labels cost no I/O."""
        return [(c, codec_for_attachment(c)) for c in book.calendars]

    # -- akasha articles ------------------------------------------------------

    def fetch_entity(self, database: str, collection: str, entity_id: str) -> dict:
        """Return one referenced Akasha article for display, or raise 404."""
        return self.entities.fetch(EntityRef(database, collection, entity_id))

    def search_entities(self, book_id, collection: str, query: str, database=None) -> dict:
        """Offer the articles a new scene could reference.

        Which Akasha database and collections a book uses is the writer's
        convention, not Chronos's rule, so the default scope is read off the
        scenes that already exist (see ``dominant_database``).
        """
        scope = self.entity_scope(book_id)
        database = database or scope["database"]
        return {
            "database": database,
            "collection": collection,
            "collections": scope["collections"],
            "results": self.entities.search(database, collection, query),
        }

    def entity_scope(self, book_id) -> dict:
        """Which Akasha database and collections this book's pickers search.

        The book's declared ``world`` wins when it has one: it is the only
        answer available to a book with no scenes yet, which is exactly when a
        writer needs the picker most. Books written before the field existed
        fall back to the old guess -- wherever their scenes already point (see
        ``dominant_database``) -- so nothing has to be migrated.

        Collections come from the world itself rather than from the scenes, so a
        new book offers the categories that are actually there instead of an
        empty list. Filtering them to what the caller may read is the web
        layer's job; this seam has no request identity.
        """
        book = self._book(book_id)
        refs = [
            ref
            for event in self._events_by_id(book_id).values()
            for ref in event.entity_refs()
        ]
        if book.world:
            return {
                "database": book.world,
                "collections": self.entities.collections(book.world),
                "declared": True,
            }
        database = dominant_database((r.database for r in refs), book_id)
        return {
            "database": database,
            "collections": sorted({r.collection for r in refs if r.database == database}),
            "declared": False,
        }

    def list_worlds(self) -> list[dict]:
        """Every Akasha world, each with its collections, for the book form's
        picker. Unfiltered -- the route narrows it to what the caller can read.

        Not book-scoped, because the writer chooses a world while *creating* a
        book, when there is no book to scope to.
        """
        return [
            {"database": name, "collections": self.entities.collections(name)}
            for name in self.entities.worlds()
        ]
