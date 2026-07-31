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


def validate_order(events_in_order: list[Event]) -> Violation | None:
    """Return the first adjacent pair where ``end(prev) > start(next)``, else None."""
    for prev, nxt in pairwise(events_in_order):
        if prev.end_tick > nxt.start_tick:
            return Violation(prev.id, nxt.id, prev.end_tick, nxt.start_tick)
    return None
