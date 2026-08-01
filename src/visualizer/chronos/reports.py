"""Whole-book invariant aggregation (design §7.3) -- pure, no I/O.

Composes the three story-logic checks over a book's events and plotlines into
one report. Under the all-soft model (§8.1) this is what `status` and
`/validate` are built from -- the same functions used everywhere else, just run
across the whole book. Services load the data; this module only computes.

Every check runs on **effective paths** (``continuation``), so a thread stored
as a segment plus a ``continues_into`` is judged on the full path it actually
follows -- including the junction into the continuation it joins.
"""

from dataclasses import dataclass, field

from .book_rules import ConvergenceReport, validate_convergence
from .conflicts import Conflict, all_conflicts
from .continuation import effective_paths
from .models import Event, Plotline
from .ordering import Violation, validate_order
from .scheduling import Window, unscheduled_windows


@dataclass
class OrderingIssue:
    plotline: str
    violation: Violation


@dataclass
class BookReport:
    temporal_conflicts: list[Conflict] = field(default_factory=list)
    ordering: list[OrderingIssue] = field(default_factory=list)
    convergence: ConvergenceReport | None = None
    unscheduled: dict[str, Window] = field(default_factory=dict)

    @property
    def impossible_windows(self) -> dict[str, Window]:
        """Unscheduled scenes their neighbours leave no room for."""
        return {eid: w for eid, w in self.unscheduled.items() if w.impossible}

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
    events: list[Event], plotlines: list[Plotline], terminus: str | None
) -> BookReport:
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
    )
