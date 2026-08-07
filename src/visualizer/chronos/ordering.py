"""Plotline ordering validation (design §5.2) -- pure, no I/O.

Rule: if A precedes B in a plotline, A must end before B begins. With half-open
intervals (§4), *touching* is allowed, so the violation is ``end(prev) >
start(next)``. Checking adjacent pairs is sufficient for the full pairwise rule
(see the design), so this is an O(n) scan.
"""

from dataclasses import dataclass
from itertools import pairwise

from .models import Event


@dataclass
class Violation:
    """The first adjacent pair that is out of order."""

    before_id: str
    after_id: str
    before_end: int
    after_start: int

    @property
    def reason(self) -> str:
        return f"end({self.before_end}) > start({self.after_start})"


def all_violations(events_in_order: list[Event]) -> list[Violation]:
    """Every out-of-order pair, in path order.

    Unscheduled scenes are skipped: a scene with no timing yet cannot be out of
    order, and the scheduled scenes around it must still run forwards.

    ``validate_order`` answers "is this thread sound?" and stops at the first
    problem. An editor asks a different question -- "which scenes should I mark?"
    -- and needs them all, so reordering one pair does not hide the next.
    """
    return [
        Violation(prev.id, nxt.id, prev.end_tick, nxt.start_tick)
        for prev, nxt in pairwise([e for e in events_in_order if e.is_scheduled])
        if prev.end_tick > nxt.start_tick
    ]


def validate_order(events_in_order: list[Event]) -> Violation | None:
    """Return the first out-of-order pair, else None."""
    violations = all_violations(events_in_order)
    return violations[0] if violations else None
