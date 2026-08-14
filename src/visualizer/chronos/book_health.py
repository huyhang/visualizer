"""Every problem in one book, in one list (design §5, §8.1) -- pure, no I/O.

``plotline_health`` answers "which scene on *this thread* should I mark?", and
the plotline view asks it once per thread. A writer who wants to know what is
wrong with the *book* would otherwise have to open every thread in turn, so this
module asks the same question of all of them at once and folds the answers into
one report.

It is built from the per-scene ``Finding`` vocabulary rather than from
``reports``/``/validate`` on purpose. Those speak in ids and categories, which is
right for a machine and wrong for a reader; findings are already written for a
novelist, already name the Akasha articles they quote, and are already what the
timeline and the editor say. Reusing them is what keeps the book report from
inventing a second way to describe the same contradiction.

Three things follow from folding per-thread answers together:

* **A problem is one problem, however many threads see it.** Two scenes putting
  a character in two places are reported on both scenes and on every thread
  either of them sits on; here they collapse to a single issue that *names* the
  threads. The identity used to collapse them is the one ``conflict_count``
  already uses, so the number a thread contributes here and the number the
  plotline table prints for it cannot disagree.
* **A finding is phrased from its scene's point of view** ("this scene has not
  ended when 'X' begins"), which only reads correctly next to that scene. So
  every issue carries the ``scene`` it is anchored to, and the report shows the
  two together.
* **Scenes on no thread still count.** A scene written and never threaded is
  invisible to every per-thread pass, but ``/validate`` sees it and so does the
  writer -- so each is checked as a path of its own.

Severity keeps the meaning ``reports.BookReport.ok`` gives it, so that a book the
report calls conflicted is exactly a book whose card says ``conflicted``. The
contradictions are ``conflict``; an undated scene is ``info``, because it is a
draft state rather than a fault; and a broken continuation chain is ``info`` too,
which is how the plotline view already renders it -- writes refuse to create one,
so it is a state a book can only fall into sideways, never one a writer is
working in.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from .book_rules import validate_convergence
from .calendar import TimeCodec
from .continuation import Resolution
from .models import EntityRef, Event
from .plotline_health import CONFLICT, INFO, Finding, findings_for_path

_DESIGN = "docs/chronos/design.md"


@dataclass(frozen=True)
class Issue:
    """One problem in a book, wherever in it the problem lives."""

    code: str
    severity: str
    message: str
    # The scene the message is said about ("this scene..."), when there is one.
    # Book-wide issues -- no ending designated, a thread that cannot be
    # resolved -- have none.
    scene: str | None = None
    events: tuple[str, ...] = field(default=())      # other scenes named
    plotlines: tuple[str, ...] = field(default=())   # threads this lands on
    refs: tuple[EntityRef, ...] = field(default=())  # Akasha articles quoted
    doc: str | None = None


def book_issues(
    resolutions: dict[str, Resolution],
    events_by_id: dict[str, Event],
    codec: TimeCodec,
    missing_refs: Iterable[EntityRef] = (),
    terminus: str | None = None,
) -> list[Issue]:
    """Everything wrong with one book, in story order.

    :param resolutions: every thread's ``continuation.resolve`` result -- the
        resolved paths the rules run on, *and* the reason a chain is broken when
        one is. Taken together rather than as bare paths so the two cannot be
        computed from different data.
    :param events_by_id: every scene in the book, including ones no thread uses.
    :param missing_refs: Akasha articles already found to be gone (existence is
        I/O; this module only decides what to say about it).
    """
    paths = {pid: r.events for pid, r in resolutions.items()}
    issues = [
        *_scene_issues(paths, events_by_id, codec, missing_refs),
        *_convergence_issues(paths, terminus, events_by_id),
        *_continuation_issues(resolutions),
    ]
    return sorted(issues, key=_reading_order(events_by_id))


# -- per-scene findings, folded across every thread --------------------------


def _scene_issues(paths, events_by_id, codec, missing_refs) -> list[Issue]:
    merged: dict[tuple, Issue] = {}
    for plotline_id in sorted(paths):
        path = paths[plotline_id]
        found = findings_for_path(path, events_by_id, paths, codec, missing_refs)
        for event_id in path:
            for finding in found.get(event_id, ()):
                _fold(merged, finding, event_id, plotline_id)
    # A scene no thread lists is on no path, so no pass above has looked at it.
    # As a path of its own it still answers for its cast and its references;
    # ordering needs a neighbour and stays quiet, which is correct.
    for event_id in _unthreaded(paths, events_by_id):
        found = findings_for_path([event_id], events_by_id, paths, codec, missing_refs)
        for finding in found.get(event_id, ()):
            _fold(merged, finding, event_id, None)
    return list(merged.values())


def _fold(merged: dict, finding: Finding, event_id: str, plotline_id: str | None) -> None:
    """Add a finding to the report, or note another thread that already has it.

    Identity is the code plus the set of scenes involved -- the same key
    ``conflict_count`` uses -- so both ends of a pair problem, and every thread
    that can see it, come to the one issue. The first sighting supplies the
    wording, and iteration is ordered (threads by id, scenes along the path), so
    which one that is does not vary between two reads of the same book.
    """
    key = (finding.code, frozenset((event_id, *finding.events)))
    existing = merged.get(key)
    if existing is None:
        merged[key] = Issue(
            code=finding.code,
            severity=finding.severity,
            message=finding.message,
            scene=event_id,
            events=finding.events,
            plotlines=() if plotline_id is None else (plotline_id,),
            refs=finding.refs,
            doc=finding.doc,
        )
    elif plotline_id is not None and plotline_id not in existing.plotlines:
        merged[key] = replace(existing, plotlines=(*existing.plotlines, plotline_id))


def _unthreaded(paths: dict[str, list[str]], events_by_id: dict[str, Event]) -> list[str]:
    threaded = {event_id for path in paths.values() for event_id in path}
    return sorted(set(events_by_id) - threaded)


# -- whole-thread verdicts no scene can carry --------------------------------


def _convergence_issues(paths, terminus, events_by_id) -> list[Issue]:
    """The third story rule (§5.3): every thread ends where the book does."""
    report = validate_convergence(paths, terminus)
    return [_convergence_issue(f, terminus, events_by_id) for f in report.failures]


def _convergence_issue(failure: dict, terminus, events_by_id) -> Issue:
    if failure["reason"] == "no terminus designated":
        return Issue(
            code="NO_TERMINUS",
            severity=CONFLICT,
            message=(
                "No scene is marked as this book's ending, so no thread can be "
                "checked against one. Open a plotline and mark its last scene "
                "with ✦."
            ),
            doc=f"{_DESIGN}#53",
        )
    if failure["reason"] == "empty plotline":
        return Issue(
            code="EMPTY_PLOTLINE",
            severity=CONFLICT,
            message="This plotline has no scenes on it, so it reaches no ending.",
            plotlines=(failure["plotline"],),
            doc=f"{_DESIGN}#53",
        )
    last = failure.get("last_event")
    return Issue(
        code="TERMINUS_VIOLATION",
        severity=CONFLICT,
        message=(
            f"This plotline stops at '{_title(events_by_id, last)}' rather than "
            f"reaching the book's ending, '{_title(events_by_id, terminus)}'."
        ),
        events=() if last is None else (last,),
        plotlines=(failure["plotline"],),
        doc=f"{_DESIGN}#53",
    )


def _continuation_issues(resolutions: dict[str, Resolution]) -> list[Issue]:
    """Threads whose ``continues_into`` chain cannot be followed (§3.3)."""
    return [
        issue
        for plotline_id in sorted(resolutions)
        if (issue := _continuation_issue(plotline_id, resolutions[plotline_id]))
    ]


def _continuation_issue(plotline_id: str, resolution: Resolution) -> Issue | None:
    if resolution.cycle:
        return _broken(
            plotline_id, "PLOTLINE_CYCLE",
            "This plotline's continuation chain loops: "
            + " → ".join(resolution.cycle) + ".",
        )
    if resolution.missing:
        return _broken(
            plotline_id, "INVALID_PLOTLINE",
            f"This plotline continues into '{resolution.missing}', "
            "which does not exist.",
        )
    if resolution.anchor_missing:
        return _broken(
            plotline_id, "INVALID_PLOTLINE",
            f"This plotline joins its continuation at '{resolution.anchor_missing}', "
            "which is no longer on that thread's path.",
        )
    return None


def _broken(plotline_id: str, code: str, message: str) -> Issue:
    return Issue(
        code=code, severity=INFO, message=message,
        plotlines=(plotline_id,), doc=f"{_DESIGN}#33",
    )


# -- ordering ----------------------------------------------------------------


def _title(events_by_id: dict[str, Event], event_id: str | None) -> str:
    event = events_by_id.get(event_id) if event_id else None
    return event.display_title if event else (event_id or "nothing")


def _reading_order(events_by_id: dict[str, Event]):
    """Story order: dated scenes first by when they happen, then the rest by id.

    The same convention the scene library uses, and for the same reason -- a
    report read top to bottom should follow the book, not the alphabet. Issues
    anchored to no scene sort with the undated ones; the report groups by kind
    before it shows them, so only order *within* a group is visible.
    """
    def key(issue: Issue):
        event = events_by_id.get(issue.scene) if issue.scene else None
        if event is not None and event.is_scheduled:
            return (0, event.start_tick, issue.scene, issue.code)
        return (1, 0, issue.scene or "", issue.code)

    return key
