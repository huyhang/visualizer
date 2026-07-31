"""Whole-book invariant aggregation (design §7.3) -- pure, no I/O.

Composes the three story-logic checks over a book's events and plotlines into
one report. Under the all-soft model (§8.1) this is what `status` and
`/validate` are built from -- the same functions used everywhere else, just run
across the whole book. Services load the data; this module only computes.
"""

from dataclasses import dataclass, field

from .book_rules import ConvergenceReport, validate_convergence
from .conflicts import Conflict, all_conflicts
from .models import Event, Plotline
from .ordering import Violation, validate_order


@dataclass
class OrderingIssue:
    plotline: str
    violation: Violation


@dataclass
class BookReport:
    temporal_conflicts: list[Conflict] = field(default_factory=list)
    ordering: list[OrderingIssue] = field(default_factory=list)
    convergence: ConvergenceReport | None = None

    @property
    def ok(self) -> bool:
        return (
            not self.temporal_conflicts
            and not self.ordering
            and (self.convergence is None or self.convergence.ok)
        )


def _ordered_events(plotline: Plotline, by_id: dict[str, Event]) -> list[Event]:
    return [by_id[eid] for eid in plotline.events if eid in by_id]


def plotline_ordering_issue(plotline: Plotline, by_id: dict[str, Event]) -> OrderingIssue | None:
    violation = validate_order(_ordered_events(plotline, by_id))
    return OrderingIssue(plotline.id, violation) if violation else None


def build_report(
    events: list[Event], plotlines: list[Plotline], terminus: str | None
) -> BookReport:
    by_id = {e.id: e for e in events}
    ordering = [
        issue
        for pl in plotlines
        if (issue := plotline_ordering_issue(pl, by_id)) is not None
    ]
    return BookReport(
        temporal_conflicts=all_conflicts(events),
        ordering=ordering,
        convergence=validate_convergence(plotlines, terminus),
    )
