"""Temporal-conflict detection (design §5.1) -- pure, no I/O.

Rule: a character cannot be in two events at *different* locations with
*overlapping* timeframes. Same-location overlaps are allowed, and scenes that
are not scheduled yet are skipped -- they have no interval to overlap. The service loads
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
    # An unscheduled scene has no interval, so it can contradict nothing.
    if not (candidate.is_scheduled and other.is_scheduled):
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


def _by_character(events: list[Event]) -> dict[EntityRef, list[int]]:
    """Positions of the scheduled events each character appears in.

    Only scenes sharing a character can possibly conflict, so this index is what
    lets ``all_conflicts`` skip the pairs that never had a chance. Unscheduled
    scenes have no interval and are left out entirely.
    """
    buckets: dict[EntityRef, list[int]] = {}
    for position, event in enumerate(events):
        if not event.is_scheduled:
            continue
        for character in set(event.characters):
            buckets.setdefault(character, []).append(position)
    return buckets


def all_conflicts(events: list[Event]) -> list[Conflict]:
    """Every conflicting unordered pair across a whole book (each pair once).

    Two filters, both exact, so the result is identical to comparing all
    n(n-1)/2 pairs -- just without doing that:

    * a conflict *requires a shared character*, so only scenes that share one are
      ever compared (``_by_character``);
    * within one character, a conflict *requires overlapping time*, so their
      scenes are swept in start order and the scan stops at the first scene that
      begins after the current one ends -- nothing later can reach back.

    A book whose scenes mostly run one after another therefore costs about what
    it takes to read them, rather than the square of their number. Pairs are
    still returned in input order, so the report reads exactly the same.
    """
    pairs: set[tuple[int, int]] = set()
    for positions in _by_character(events).values():
        in_time = sorted(positions, key=lambda p: events[p].start_tick)
        for index, first in enumerate(in_time):
            ends = events[first].end_tick
            for second in in_time[index + 1 :]:
                if events[second].start_tick >= ends:
                    break  # sorted by start: no later scene can overlap either
                pairs.add((min(first, second), max(first, second)))

    found = (_conflicts_with(events[i], events[j]) for i, j in sorted(pairs))
    return [c for c in found if c is not None]
