"""Whole-book invariant aggregation (design §7.3) -- pure, no I/O.

Composes the whole-book checks over a book's events and plotlines into one
report: the three story-logic rules, plus whether the Akasha articles the scenes
name still exist (the one thing here that needs an answer from outside, so the
caller resolves it and passes it in -- see ``build_report``).

Under the all-soft model (§8.1) this is what `status` and `/validate` are built
from -- the same functions used everywhere else, just run across the whole book.
Services load the data; this module only computes.

Every check runs on **effective paths** (``continuation``), so a thread stored
as a segment plus a ``continues_into`` is judged on the full path it actually
follows -- including the junction into the continuation it joins.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from .book_rules import ConvergenceReport, validate_convergence
from .conflicts import Conflict, all_conflicts
from .continuation import effective_paths
from .goal_rules import goal_findings
from .models import EntityRef, Event, Goal, Plotline
from .ordering import Violation, validate_order
from .scheduling import Window, unscheduled_windows
from .severity import CONFLICT


@dataclass
class OrderingIssue:
    plotline: str
    violation: Violation


@dataclass(frozen=True)
class MissingEntity:
    """A scene pointing at an Akasha article that is no longer there.

    Writes already refuse an unknown reference, so this can only be an article
    deleted *after* the scene naming it was written -- which nothing tells the
    writer at the time, because Akasha holds no back-reference to Chronos.
    """

    event: str
    role: str  # "location" | "character" | "item"
    ref: EntityRef


def entity_roles(event: Event) -> list[tuple[str, EntityRef]]:
    """This scene's references, each labelled by the part it plays in it.

    The role is what makes the finding actionable: a missing *location* leaves
    the scene nowhere, while a missing character is one name out of a cast.
    """
    return [
        ("location", event.location),
        *(("character", ref) for ref in event.characters),
        *(("item", ref) for ref in event.items),
    ]


def dangling_references(
    events: Iterable[Event], missing_refs: Iterable[EntityRef]
) -> list[MissingEntity]:
    """Which scenes point at articles that are gone.

    Takes the refs *already known* to be missing rather than looking anything
    up: existence is I/O, so the service asks the entity gate once for the whole
    book and this stays pure. Ordered by scene, then by the order the refs
    appear on it, so the report reads the same way twice.
    """
    gone = set(missing_refs)
    if not gone:
        return []
    return [
        MissingEntity(event.id, role, ref)
        for event in sorted(events, key=lambda e: e.id)
        for role, ref in entity_roles(event)
        if ref in gone
    ]


@dataclass
class BookReport:
    temporal_conflicts: list[Conflict] = field(default_factory=list)
    ordering: list[OrderingIssue] = field(default_factory=list)
    convergence: ConvergenceReport | None = None
    unscheduled: dict[str, Window] = field(default_factory=dict)
    missing_entities: list[MissingEntity] = field(default_factory=list)
    # Everything ``goal_rules`` has to say about the book's goals, notes
    # included. Kept whole rather than filtered to the faults so ``/validate``
    # can list them all, exactly as it lists unscheduled scenes.
    goal_findings: list = field(default_factory=list)

    @property
    def impossible_windows(self) -> dict[str, Window]:
        """Unscheduled scenes their neighbours leave no room for."""
        return {eid: w for eid, w in self.unscheduled.items() if w.impossible}

    @property
    def goal_conflicts(self) -> list:
        """The goal findings that are contradictions rather than draft states.

        Most goal findings are notes -- nobody is pursuing it yet, no scene
        delivers it yet -- and counting those would leave every book in progress
        red, the same trap an unscheduled scene would spring.
        """
        return [f for f in self.goal_findings if f.severity == CONFLICT]

    @property
    def ok(self) -> bool:
        """Whether the story holds together.

        Note an unscheduled scene is **not** a problem -- it is a draft state,
        and counting it as one would leave the book permanently red and train
        the writer to ignore the report. A scene with *no possible time*,
        however, is a genuine contradiction.
        """
        return (
            not self.temporal_conflicts
            and not self.ordering
            and not self.impossible_windows
            and not self.missing_entities
            and not self.goal_conflicts
            and (self.convergence is None or self.convergence.ok)
        )


def ordered_events(event_ids: list[str], by_id: dict[str, Event]) -> list[Event]:
    """The Event objects for a path, skipping ids that no longer resolve."""
    return [by_id[eid] for eid in event_ids if eid in by_id]


def path_ordering_issue(
    plotline_id: str, event_ids: list[str], by_id: dict[str, Event]
) -> OrderingIssue | None:
    violation = validate_order(ordered_events(event_ids, by_id))
    return OrderingIssue(plotline_id, violation) if violation else None


def build_report(
    events: list[Event],
    plotlines: list[Plotline],
    terminus: str | None,
    missing_refs: Iterable[EntityRef] = (),
    goals: Iterable[Goal] = (),
) -> BookReport:
    """Compose every whole-book check.

    ``missing_refs`` is the one thing this module cannot work out for itself --
    whether an Akasha article still exists is I/O — so the caller resolves it and
    passes the answer in. Defaulting to "none reported" keeps the pure checks
    callable on their own, which is how they are unit tested.

    ``goals`` defaults to none for the same reason, and is judged here rather
    than only in the reader's report so that one thing decides a book's verdict.
    A goal contradiction that reached the report but not this function would
    give a book a card saying ``consistent`` above a page listing its faults.
    """
    by_id = {e.id: e for e in events}
    paths = effective_paths(plotlines)
    ordering = [
        issue
        for pid in sorted(paths)
        if (issue := path_ordering_issue(pid, paths[pid], by_id)) is not None
    ]
    return BookReport(
        temporal_conflicts=all_conflicts(events),
        ordering=ordering,
        convergence=validate_convergence(paths, terminus),
        unscheduled=unscheduled_windows(events, paths),
        missing_entities=dangling_references(events, missing_refs),
        goal_findings=goal_findings(goals, plotlines, by_id, paths),
    )
