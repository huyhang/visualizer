"""Resolving plotline continuations (design §3.3) -- pure, no I/O.

A plotline stores only its *own* segment of events plus an optional
``continues_into`` pointing at another plotline. Its **effective path** is its
own events followed by the effective path of that continuation, transitively --
so a shared ending lives in one plotline instead of being repeated in every
thread that reaches it.

Everything downstream (ordering, convergence, the story graph) runs on the
effective path, so resolution happens here, once, and the rest of the code never
has to know a plotline was stored in pieces.

The resolver is deliberately **cycle-tolerant**: it reports a cycle rather than
recursing forever, because a read must never hang on data that is already bad.
"""

from dataclasses import dataclass, field

from .models import Plotline


@dataclass
class Resolution:
    """A plotline's effective path, or why it could not be resolved."""

    events: list[str] = field(default_factory=list)
    chain: list[str] = field(default_factory=list)  # plotline ids walked, self first
    cycle: list[str] | None = None                  # the looping ids, if any
    missing: str | None = None                      # continuation target that doesn't exist

    @property
    def ok(self) -> bool:
        return self.cycle is None and self.missing is None


def resolve(plotline_id: str, by_id: dict[str, Plotline]) -> Resolution:
    """Follow ``continues_into`` from ``plotline_id``, concatenating events."""
    events: list[str] = []
    chain: list[str] = []
    seen: set[str] = set()
    current: str | None = plotline_id
    while current is not None:
        if current in seen:
            start = chain.index(current)
            return Resolution(events, chain, cycle=[*chain[start:], current])
        plotline = by_id.get(current)
        if plotline is None:
            return Resolution(events, chain, missing=current)
        seen.add(current)
        chain.append(current)
        events.extend(plotline.events)
        current = plotline.continues_into
    return Resolution(events, chain)


def resolve_all(plotlines: list[Plotline]) -> dict[str, Resolution]:
    """Resolve every plotline in a book, keyed by id."""
    by_id = {p.id: p for p in plotlines}
    return {p.id: resolve(p.id, by_id) for p in plotlines}


def effective_paths(plotlines: list[Plotline]) -> dict[str, list[str]]:
    """Just the resolved event lists -- what the graph and the rules consume."""
    return {pid: r.events for pid, r in resolve_all(plotlines).items()}


def would_cycle(candidate: Plotline, plotlines: list[Plotline]) -> list[str] | None:
    """Return the cycle ``candidate`` would create, or None if it is safe.

    Used to reject a write *before* it is persisted: unlike a story-logic
    finding, an unresolvable chain would break every later read.
    """
    by_id = {p.id: p for p in plotlines}
    by_id[candidate.id] = candidate
    return resolve(candidate.id, by_id).cycle
