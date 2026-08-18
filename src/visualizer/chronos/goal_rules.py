"""What a book is trying to bring about, and whether it does (design §3.5) --
pure, no I/O.

Goals are the book's third graph. The scenes form one (ordered by tick), the
plotline continuations another (ordered by structure), and the goals a third,
ordered by *dependency*: a coronation rests on a claim being proved, which rests
on a witness being found. None of that touches the timeline until a goal names
the scene that delivers it -- and that single anchor, ``Goal.achieved_at``, is
what turns an intention into something the continuity checker can judge.

Everything here is derived. A goal stores what it is, what it rests on, and
where it lands; whether it is *met* is worked out from the book each time it is
asked, so there is no stored verdict to fall out of step with the story.

The findings follow the vocabulary the rest of Chronos uses (§8.1): a
contradiction is a ``conflict``, and a draft state is an ``info``. Two of these
are contradictions -- a goal whose achieving scene no thread pursuing it ever
reaches, and a goal met before something it depends on. The rest are notes: a
goal nobody pursues yet, one with no scene yet, one whose prerequisite has not
been placed. A writer three chapters in has many of those and no faults, and a
report that called them faults would be ignored by the fourth chapter.

Two codes describe data that no write can produce -- a dependency on a goal that
does not exist, and a loop -- because the service refuses both. They are
reported rather than assumed away for the same reason a broken continuation is:
a record can still get there sideways (a delete elsewhere, an older client), and
a reader that cannot describe the state it is in is worse than one that can.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from .models import Event, Goal, Plotline
from .phrasing import is_are, quoted_names
from .severity import CONFLICT, INFO

_DESIGN = "docs/chronos/design.md#35"


@dataclass(frozen=True)
class GoalFinding:
    """One thing worth saying about one goal.

    ``goal`` is what the message is said *about* ("this goal..."), the way a
    scene finding is phrased from its scene's point of view. It is ``None`` for
    the one finding that belongs to a thread instead: a plotline naming a goal
    the book does not have.
    """

    code: str
    severity: str
    message: str
    goal: str | None = None
    goals: tuple[str, ...] = field(default=())      # other goals named
    events: tuple[str, ...] = field(default=())     # scenes named
    plotlines: tuple[str, ...] = field(default=())  # threads this lands on
    doc: str | None = _DESIGN


# -- the dependency graph ----------------------------------------------------


def served_by(goals: Iterable[Goal], plotlines: Iterable[Plotline]) -> dict[str, list[str]]:
    """Which threads pursue each goal, keyed by goal id.

    The reverse of ``Plotline.goals``, computed rather than stored: one
    direction of an edge is the whole truth, and a second copy is only a second
    thing to keep in step.
    """
    out: dict[str, list[str]] = {goal.id: [] for goal in goals}
    for plotline in sorted(plotlines, key=lambda p: p.id):
        for goal_id in plotline.goals:
            if goal_id in out:
                out[goal_id].append(plotline.id)
    return out


def dependency_cycle(candidate: Goal, goals: Iterable[Goal]) -> list[str] | None:
    """The loop saving ``candidate`` would create, or None if it is safe.

    Used to refuse a write before it is persisted, the way ``would_cycle`` does
    for continuations: a goal that must be met before itself is not a story
    problem to report, it is a statement with no meaning.
    """
    by_id = {goal.id: goal for goal in goals}
    by_id[candidate.id] = candidate
    return _cycle_from(candidate.id, by_id)


def dependency_cycles(goals: Iterable[Goal]) -> dict[str, list[str]]:
    """The loop each goal sits in, for the goals that sit in one.

    Reported per goal rather than per loop, so a reader looking at any goal in
    the ring is told, on that goal, what it is caught in -- the same choice
    ``book_health`` makes for a looping continuation chain.
    """
    by_id = {goal.id: goal for goal in goals}
    found = {}
    for goal_id in sorted(by_id):
        cycle = _cycle_from(goal_id, by_id)
        # A loop *reachable from* this goal is not a loop this goal is in; only
        # the second is worth saying here, and a walk that returns to where it
        # started is exactly the difference.
        if cycle is not None and cycle[0] == goal_id:
            found[goal_id] = cycle
    return found


def _cycle_from(start: str, by_id: dict[str, Goal]) -> list[str] | None:
    """Depth-first walk of ``depends_on``, returning the first loop it closes.

    The loop is returned as the ids around it, first repeated at the end, so it
    prints as ``a → b → a``.
    """
    path: list[str] = []
    on_path: set[str] = set()
    settled: set[str] = set()

    def walk(goal_id: str) -> list[str] | None:
        if goal_id in on_path:
            return [*path[path.index(goal_id):], goal_id]
        if goal_id in settled or goal_id not in by_id:
            return None
        path.append(goal_id)
        on_path.add(goal_id)
        for dependency in by_id[goal_id].depends_on:
            closed = walk(dependency)
            if closed is not None:
                return closed
        path.pop()
        on_path.discard(goal_id)
        settled.add(goal_id)
        return None

    return walk(start)


def depths(goals: Iterable[Goal]) -> dict[str, int]:
    """How deep each goal sits in the dependency graph, for laying it out.

    Zero for a goal that rests on nothing; otherwise one past the deepest thing
    it rests on -- the longest path rather than the shortest, so a goal always
    draws below *everything* it depends on rather than merely below the nearest.

    Cycle-tolerant, like every other reader here: an edge that closes a loop is
    ignored for depth rather than followed forever. The drawing of bad data is
    then merely arbitrary instead of absent, and the loop itself is reported.
    """
    by_id = {goal.id: goal for goal in goals}
    known: dict[str, int] = {}

    def depth_of(goal_id: str, on_path: frozenset[str]) -> int:
        if goal_id in known:
            return known[goal_id]
        goal = by_id.get(goal_id)
        if goal is None or goal_id in on_path:
            return 0
        below = [
            depth_of(dependency, on_path | {goal_id})
            for dependency in goal.depends_on
            if dependency in by_id
        ]
        # Only the outermost walk memoises. A depth computed *inside* another
        # walk may have been truncated by that walk's cycle guard, and a
        # truncated value cached is one every later reader inherits. Books hold
        # tens of goals, so the repeated work costs less than that bookkeeping.
        depth = 1 + max(below) if below else 0
        if not on_path:
            known[goal_id] = depth
        return depth

    return {goal_id: depth_of(goal_id, frozenset()) for goal_id in sorted(by_id)}


# -- findings ----------------------------------------------------------------


def goal_findings(
    goals: Iterable[Goal],
    plotlines: Iterable[Plotline],
    events_by_id: dict[str, Event],
    paths: dict[str, list[str]],
) -> list[GoalFinding]:
    """Everything worth saying about a book's goals, in goal order.

    :param paths: every thread's *effective* path, so a goal achieved on a scene
        a thread only inherits through a continuation counts as reached -- the
        same path every other rule is judged on.
    """
    goals = sorted(goals, key=lambda g: g.id)
    by_id = {goal.id: goal for goal in goals}
    threads = served_by(goals, plotlines)
    cycles = dependency_cycles(goals)

    found: list[GoalFinding] = []
    for goal in goals:
        found.extend(_findings_for(goal, by_id, threads[goal.id], events_by_id, paths))
        if goal.id in cycles:
            found.append(_cycle_finding(goal, cycles[goal.id]))
    found.extend(_unknown_goal_findings(plotlines, by_id))
    return found


def _findings_for(
    goal: Goal,
    by_id: dict[str, Goal],
    threads: list[str],
    events_by_id: dict[str, Event],
    paths: dict[str, list[str]],
) -> list[GoalFinding]:
    found = []
    if not threads:
        found.append(
            GoalFinding(
                code="GOAL_UNSERVED",
                severity=INFO,
                message=(
                    "No thread is pursuing this goal. Open a plotline and name "
                    "the goal among the ones it serves."
                ),
                goal=goal.id,
            )
        )
    missing = [d for d in goal.depends_on if d not in by_id]
    if missing:
        found.append(
            GoalFinding(
                code="GOAL_DEPENDENCY_MISSING",
                severity=INFO,
                message=(
                    f"This goal depends on {quoted_names(missing)}, which "
                    f"{is_are(missing)} no longer in this book."
                ),
                goal=goal.id,
                goals=tuple(missing),
            )
        )
    if goal.achieved_at is None:
        found.append(
            GoalFinding(
                code="GOAL_UNACHIEVED",
                severity=INFO,
                message="No scene achieves this goal yet.",
                goal=goal.id,
            )
        )
        return found
    reach = _reach_finding(goal, threads, events_by_id, paths)
    if reach is not None:
        found.append(reach)
    found.extend(_dependency_timing(goal, by_id, events_by_id))
    return found


def _reach_finding(
    goal: Goal, threads: list[str], events_by_id: dict[str, Event], paths
) -> GoalFinding | None:
    """Whether the story, as threaded, actually arrives at this goal's scene.

    Silent when no thread pursues the goal at all: that is already said once,
    and saying it twice in two vocabularies is how a report stops being read.
    """
    scene = events_by_id.get(goal.achieved_at)
    if scene is None:
        return GoalFinding(
            code="GOAL_NOT_REACHED",
            severity=CONFLICT,
            message=(
                f"This goal is achieved at '{goal.achieved_at}', which is no "
                "longer a scene in this book."
            ),
            goal=goal.id,
            events=(goal.achieved_at,),
        )
    if not threads:
        return None
    if any(goal.achieved_at in paths.get(pid, ()) for pid in threads):
        return None
    return GoalFinding(
        code="GOAL_NOT_REACHED",
        severity=CONFLICT,
        message=(
            f"This goal is achieved at '{scene.display_title}', but no thread "
            "pursuing it passes through that scene."
        ),
        goal=goal.id,
        events=(goal.achieved_at,),
        plotlines=tuple(threads),
    )


def _dependency_timing(
    goal: Goal, by_id: dict[str, Goal], events_by_id: dict[str, Event]
) -> list[GoalFinding]:
    """An achieved goal against the goals it rests on (the point of the anchor).

    Two things can be wrong once this goal has a scene. Something it depends on
    may have no scene at all -- a note, because the writer has simply not placed
    it yet -- or it may have one that has not finished by the time this goal is
    met, which is the contradiction: the story delivers the payoff before what
    it was built on.

    Compared with the same half-open rule as scene ordering (§5.2), so touching
    is allowed, and skipped where either scene is unscheduled -- a scene with no
    timing cannot be too late.
    """
    scene = events_by_id.get(goal.achieved_at)
    found = []
    for dependency_id in goal.depends_on:
        dependency = by_id.get(dependency_id)
        if dependency is None:
            continue  # already reported as a missing dependency
        if dependency.achieved_at is None:
            found.append(
                GoalFinding(
                    code="GOAL_DEPENDENCY_UNMET",
                    severity=INFO,
                    message=(
                        f"This goal is achieved, but '{dependency.display_title}', "
                        "which it depends on, is not achieved anywhere yet."
                    ),
                    goal=goal.id,
                    goals=(dependency_id,),
                )
            )
            continue
        before = events_by_id.get(dependency.achieved_at)
        if before is None or scene is None or before.id == scene.id:
            continue
        if not (before.is_scheduled and scene.is_scheduled):
            continue
        if before.end_tick <= scene.start_tick:
            continue
        found.append(
            GoalFinding(
                code="GOAL_OUT_OF_ORDER",
                severity=CONFLICT,
                message=(
                    f"This goal is achieved at '{scene.display_title}', but "
                    f"'{dependency.display_title}' — which it depends on — is not "
                    f"achieved until '{before.display_title}', which has not ended "
                    "by then."
                ),
                goal=goal.id,
                goals=(dependency_id,),
                events=(scene.id, before.id),
            )
        )
    return found


def _cycle_finding(goal: Goal, cycle: list[str]) -> GoalFinding:
    return GoalFinding(
        code="GOAL_CYCLE",
        severity=INFO,
        message="This goal's dependencies loop: " + " → ".join(cycle) + ".",
        goal=goal.id,
        goals=tuple(cycle[:-1]),
    )


def _unknown_goal_findings(
    plotlines: Iterable[Plotline], by_id: dict[str, Goal]
) -> list[GoalFinding]:
    """Threads naming a goal the book does not have.

    Writes refuse an unknown goal, so a book can only reach this state sideways
    -- the same way a continuation comes to point at nothing. Reported on the
    thread rather than passed over, because that is where the id is stored and
    where the writer would go to fix it.
    """
    found = []
    for plotline in sorted(plotlines, key=lambda p: p.id):
        unknown = [g for g in plotline.goals if g not in by_id]
        if not unknown:
            continue
        found.append(
            GoalFinding(
                code="GOAL_UNKNOWN",
                severity=INFO,
                message=(
                    f"This thread serves {quoted_names(unknown)}, which "
                    f"{is_are(unknown)} not {'a goal' if len(unknown) == 1 else 'goals'} "
                    "in this book."
                ),
                goals=tuple(unknown),
                plotlines=(plotline.id,),
            )
        )
    return found
