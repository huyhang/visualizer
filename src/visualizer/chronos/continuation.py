"""Resolving plotline continuations (design §3.3) -- pure, no I/O.

A plotline stores only its *own* segment of events plus an optional
``continues_into`` pointing at another plotline. Its **effective path** is its
own events followed by the effective path of that continuation, transitively --
so a shared ending lives in one plotline instead of being repeated in every
thread that reaches it.

A continuation may also name **where** it joins: ``continues_into_at`` is a scene in
the target's *resolved* path, and the thread picks the target up from there
rather than from its first scene. That is what lets a thread catch up with the
trunk halfway down it without copying the trunk's opening into its own segment.
``None`` means "at the head", which is what every thread written before the
field existed says.

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
    # The anchor -- the scene a join points at -- when it is not on the
    # target's resolved path. Named for what is wrong rather than for the
    # state it leaves the thread in: the thread is detached, but the *anchor*
    # is what a reader has to go and look at.
    anchor_missing: str | None = None

    @property
    def ok(self) -> bool:
        return self.cycle is None and self.missing is None and self.anchor_missing is None


def _tail_from(path: list[str], at: str | None) -> tuple[list[str], bool]:
    """``path`` from ``at`` onward, and whether ``at`` was found at all.

    The join point is a scene *id* rather than an index because an index slides
    the moment the target gains a scene above it, silently re-pointing a join
    the writer never touched. Where an id somehow occurs twice the first wins:
    duplicates are already broken data, since a scene cannot end before itself.
    """
    if at is None:
        return list(path), True
    if at not in path:
        return [], False
    return path[path.index(at):], True


def _fold(chain: list[str], by_id: dict[str, Plotline]) -> tuple[list[str], str | None]:
    """Resolve a sound chain from its tail back, applying each hop's join point.

    Folding backwards is what makes ``continues_into_at`` mean "a scene in the
    target's *resolved* path" rather than merely "a scene the target stores
    itself" -- by the time a hop is applied, everything past it is already
    resolved. Returns the path, or the join scene that could not be found.
    """
    path = list(by_id[chain[-1]].events)
    for pid in reversed(chain[:-1]):
        this = by_id[pid]
        tail, found = _tail_from(path, this.continues_into_at)
        if not found:
            return [], this.continues_into_at
        path = [*this.events, *tail]
    return path, None


def resolve(plotline_id: str, by_id: dict[str, Plotline]) -> Resolution:
    """Follow ``continues_into`` from ``plotline_id``, concatenating events."""
    chain: list[str] = []
    seen: set[str] = set()
    current: str | None = plotline_id
    while current is not None:
        if current in seen:
            start = chain.index(current)
            return Resolution(_flat(chain, by_id), chain, cycle=[*chain[start:], current])
        plotline = by_id.get(current)
        if plotline is None:
            return Resolution(_flat(chain, by_id), chain, missing=current)
        seen.add(current)
        chain.append(current)
        current = plotline.continues_into
    path, anchor_missing = _fold(chain, by_id)
    if anchor_missing is not None:
        # Best effort for a conflicted read, exactly as for a cycle or a missing
        # target: the status says the path is not to be trusted, and a writer
        # looking at a broken thread is better served by seeing its scenes than
        # by an empty list.
        return Resolution(_flat(chain, by_id), chain, anchor_missing=anchor_missing)
    return Resolution(path, chain)


def _flat(chain: list[str], by_id: dict[str, Plotline]) -> list[str]:
    """Every own segment on the chain, unsliced -- the partial path of a break."""
    return [eid for pid in chain for eid in by_id[pid].events]


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
