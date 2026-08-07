"""Per-scene findings for one plotline (design §5, §8.1) -- pure, no I/O.

``reports`` answers a whole-*book* question -- "does this story hold together?"
-- and ``/validate`` lists the answer by category. An editor asks a narrower one:
"which **scene on this thread** should I mark, and what do I say about it?" This
module answers that, running the same rules (``conflicts``, ``ordering``,
``scheduling``, and missing article references) over one effective path and
attaching each result to the scene it belongs to.

Two deliberate differences from the book report, both because a writer is looking
at a list of scenes rather than a verdict:

* **Every** ordering violation is reported, not just the first -- otherwise
  fixing one pair silently reveals the next, and the thread looks fixed when it
  is not.
* A pair problem is reported on **both** scenes, phrased from each one's point of
  view, so whichever row the writer is looking at explains itself.

Findings are the soft, reported kind (§8.1): they never block a save. Messages
use display titles and codec-formatted ticks, because they are read by a
novelist, not a machine -- the machine-readable ids stay in ``events``.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from .calendar import TimeCodec
from .conflicts import all_conflicts, find_temporal_conflicts
from .models import EntityRef, Event
from .ordering import all_violations
from .reports import entity_roles
from .scheduling import unscheduled_windows, window_for

CONFLICT = "conflict"
INFO = "info"

_DESIGN = "docs/chronos/design.md"


@dataclass(frozen=True)
class Finding:
    """One thing worth saying about one scene on one thread."""

    code: str
    severity: str
    message: str
    events: tuple[str, ...] = field(default=())  # other scenes implicated, if any
    # Akasha articles the message names. Their *titles* live in Akasha, which
    # this module cannot see and which the reader may not be allowed to read --
    # so the message quotes their ids and a client that holds the grant swaps in
    # the real names through the article proxy. See findings.js.
    refs: tuple[EntityRef, ...] = field(default=())
    doc: str | None = None


def _names(ids: list[str]) -> str:
    """"'aldric'", "'aldric' and 'lyra'", "'aldric', 'lyra' and 'bran'".

    Every id is quoted, and that is load-bearing rather than decorative: it is
    what lets a client replace ``'aldric'`` with ``'Sir Aldric'`` by exact match,
    without risking a substring of some other word in the sentence.
    """
    quoted = [f"'{i}'" for i in ids]
    if len(quoted) <= 1:
        return "".join(quoted)
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def _conflict_findings(scene: Event, others: list[Event], title) -> list[Finding]:
    """This scene puts a shared character somewhere else at the same time (§5.1)."""
    out = []
    for conflict in find_temporal_conflicts(scene, others):
        who = _names([ref.id for ref in conflict.characters])
        out.append(
            Finding(
                code="TEMPORAL_CONFLICT",
                severity=CONFLICT,
                message=(
                    f"{who} cannot be here and in '{title(conflict.other_id)}' at "
                    f"once — that scene is at '{conflict.other_location.id}' over "
                    "an overlapping time."
                ),
                events=(conflict.other_id,),
                refs=(*conflict.characters, conflict.other_location),
                doc=f"{_DESIGN}#51",
            )
        )
    return out


def _ordering_findings(ordered: list[Event], title) -> dict[str, list[Finding]]:
    """Adjacent scenes that run backwards, reported on both ends (§5.2)."""
    by_id: dict[str, list[Finding]] = {}
    for violation in all_violations(ordered):
        before, after = violation.before_id, violation.after_id
        by_id.setdefault(after, []).append(
            Finding(
                code="ORDERING_VIOLATION",
                severity=CONFLICT,
                message=f"'{title(before)}' has not ended when this scene begins.",
                events=(before,),
                doc=f"{_DESIGN}#52",
            )
        )
        by_id.setdefault(before, []).append(
            Finding(
                code="ORDERING_VIOLATION",
                severity=CONFLICT,
                message=f"This scene has not ended when '{title(after)}' begins.",
                events=(after,),
                doc=f"{_DESIGN}#52",
            )
        )
    return by_id


def _missing_entity_findings(
    scene: Event, missing: frozenset[EntityRef]
) -> list[Finding]:
    """This scene names an Akasha article that no longer exists (§8.1).

    Referential integrity is a hard rule on write, so this can only appear by an
    article being deleted *underneath* a finished scene -- Akasha holds no
    back-reference to Chronos and cannot warn anyone at the time. Reported on
    read is the only place left to catch it.

    One finding per scene rather than per reference: the writer's next move is to
    open the scene either way, and three chips saying the same thing is noise.
    """
    gone = [(role, ref) for role, ref in entity_roles(scene) if ref in missing]
    if not gone:
        return []
    roles = ", ".join(sorted({role for role, _ in gone}))
    subject = _names([ref.id for _, ref in gone])
    verb = "is" if len(gone) == 1 else "are"
    return [
        Finding(
            code="MISSING_ENTITY",
            severity=CONFLICT,
            message=(
                f"{subject} {verb} named here ({roles}) but no longer in the "
                "article store. Restore the article, or edit this scene to stop "
                "naming it."
            ),
            refs=tuple(ref for _, ref in gone),
            doc=f"{_DESIGN}#81",
        )
    ]


def _timing_finding(
    scene: Event, paths: dict[str, list[str]], by_id: dict[str, Event], codec: TimeCodec
) -> Finding | None:
    """What the neighbouring scenes imply about an unscheduled one (§4.2).

    Silent when nothing pins it down: "no timing yet" is a draft state, not a
    problem, and saying so on every unplaced scene would train the writer to
    ignore the markers.
    """
    if scene.is_scheduled:
        return None
    window = window_for(scene.id, paths, by_id)
    if window.impossible:
        return Finding(
            code="IMPOSSIBLE_WINDOW",
            severity=CONFLICT,
            message=(
                "The surrounding scenes leave no room for this one: it would have "
                f"to start after {codec.format(window.earliest)} and end before "
                f"{codec.format(window.latest)}."
            ),
            doc=f"{_DESIGN}#42",
        )
    if window.unconstrained:
        return None
    return Finding(
        code="UNSCHEDULED",
        severity=INFO,
        message="No timing yet — " + _window_hint(window, codec),
    )


def _window_hint(window, codec: TimeCodec) -> str:
    if window.earliest is None:
        return f"its neighbours put it before {codec.format(window.latest)}."
    if window.latest is None:
        return f"its neighbours put it after {codec.format(window.earliest)}."
    return (
        f"its neighbours put it between {codec.format(window.earliest)} and "
        f"{codec.format(window.latest)}."
    )


def conflict_count(findings: dict[str, list[Finding]]) -> int:
    """How many distinct problems a thread has.

    A pair problem is reported on both scenes (so each row explains itself), and
    a temporal conflict is symmetric -- so counting raw findings would say "two
    problems" where a writer sees one. Identity is the code plus the set of
    scenes involved, which collapses both directions of a pair into one.
    """
    seen = {
        (f.code, frozenset((eid, *f.events)))
        for eid, items in findings.items()
        for f in items
        if f.severity == CONFLICT
    }
    return len(seen)


def conflict_counts(
    paths: dict[str, list[str]],
    events_by_id: dict[str, Event],
    missing_refs: Iterable[EntityRef] = (),
) -> dict[str, int]:
    """How many distinct problems every thread has, in one pass over the book.

    Same answer as ``conflict_count(findings_for_path(...))`` per thread, and a
    test holds the two to each other -- but computed once for the whole book
    instead of re-scanning every scene for every thread, which is what the
    plotline table needs. The book grows; the table should not grow with it
    multiplied by its own thread count.
    """
    events = list(events_by_id.values())
    conflicts = all_conflicts(events)
    missing = frozenset(missing_refs)
    # One per scene, matching what `_missing_entity_findings` emits.
    dangling = {
        e.id for e in events if any(ref in missing for _, ref in entity_roles(e))
    }
    impossible = {
        eid for eid, window in unscheduled_windows(events, paths).items()
        if window.impossible
    }

    counts = {}
    for plotline_id, path in paths.items():
        members = set(path)
        ordered = [events_by_id[eid] for eid in path if eid in events_by_id]
        counts[plotline_id] = (
            # A pair counts once whether one end or both sit on this thread.
            sum(1 for c in conflicts if c.this_id in members or c.other_id in members)
            + len(all_violations(ordered))
            + len(members & impossible)
            + len(members & dangling)
        )
    return counts


def findings_for_path(
    path: list[str],
    events_by_id: dict[str, Event],
    paths: dict[str, list[str]],
    codec: TimeCodec,
    missing_refs: Iterable[EntityRef] = (),
) -> dict[str, list[Finding]]:
    """Every finding for one thread's effective path, keyed by event id.

    :param path: this thread's effective path (own segment + continuation).
    :param events_by_id: **every** event in the book -- a character can be put in
        two places by a scene on a thread this one never touches, and the writer
        still needs to see it here.
    :param paths: every thread's effective path, so an unscheduled scene's window
        accounts for all the threads it appears on.
    :param missing_refs: Akasha articles the caller has already found to be gone
        (existence is I/O; this module only decides what to say about it).
    """
    missing = frozenset(missing_refs)
    ordered = [events_by_id[eid] for eid in path if eid in events_by_id]
    all_events = list(events_by_id.values())

    def title(eid: str) -> str:
        event = events_by_id.get(eid)
        return event.display_title if event else eid

    ordering = _ordering_findings(ordered, title)

    out: dict[str, list[Finding]] = {}
    for scene in ordered:
        found = [
            *_conflict_findings(scene, all_events, title),
            *ordering.get(scene.id, []),
            *_missing_entity_findings(scene, missing),
        ]
        timing = _timing_finding(scene, paths, events_by_id, codec)
        if timing is not None:
            found.append(timing)
        if found:
            out[scene.id] = found
    return out
