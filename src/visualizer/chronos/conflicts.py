"""Temporal-conflict detection (design §5.1) -- pure, no I/O.

Rule: a character cannot be in two events at *different* locations with
*overlapping* timeframes. Same-location overlaps are allowed. The service loads
the small set of events sharing a character with the candidate and passes it
here; this module never touches a database.
"""

from dataclasses import dataclass

from .models import EntityRef, Event
from .timeline import overlaps


@dataclass
class Conflict:
    """One event that puts a shared character in two places at once."""

    this_id: str
    other_id: str
    characters: list[EntityRef]
    this_location: EntityRef
    other_location: EntityRef
    this_ticks: tuple[int, int]
    other_ticks: tuple[int, int]


def _shared_characters(a: Event, b: Event) -> list[EntityRef]:
    b_chars = set(b.characters)
    return [c for c in a.characters if c in b_chars]


def _conflicts_with(candidate: Event, other: Event) -> Conflict | None:
    """A conflict exists iff they share a character, sit at different
    locations, and their timeframes overlap."""
    if other.id == candidate.id:
        return None
    if candidate.location == other.location:
        return None
    shared = _shared_characters(candidate, other)
    if not shared:
        return None
    if not overlaps(
        candidate.start_tick, candidate.end_tick, other.start_tick, other.end_tick
    ):
        return None
    return Conflict(
        this_id=candidate.id,
        other_id=other.id,
        characters=shared,
        this_location=candidate.location,
        other_location=other.location,
        this_ticks=(candidate.start_tick, candidate.end_tick),
        other_ticks=(other.start_tick, other.end_tick),
    )


def find_temporal_conflicts(candidate: Event, others: list[Event]) -> list[Conflict]:
    """Return every ``other`` event that temporally conflicts with ``candidate``."""
    found = (_conflicts_with(candidate, other) for other in others)
    return [c for c in found if c is not None]


def all_conflicts(events: list[Event]) -> list[Conflict]:
    """Every conflicting unordered pair across a whole book (each pair once)."""
    out: list[Conflict] = []
    for i, a in enumerate(events):
        for b in events[i + 1 :]:
            conflict = _conflicts_with(a, b)
            if conflict is not None:
                out.append(conflict)
    return out
