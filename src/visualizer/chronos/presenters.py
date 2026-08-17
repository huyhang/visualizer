"""Response shaping (design §6.4, §7.2, §7.4, §7.6) -- the single source of
every response dict.

Keeping this in one pure-ish place (it depends only on models + codec, never on
Flask or Mongo) means the code, the OpenAPI schema, and the examples all trace
to one definition. It turns ids into titles, ticks into codec labels, and adds
`_links` / `status` so responses explain themselves.
"""

from .book_health import Issue
from .book_rules import Neighborhood, build_graph
from .calendar import TimeCodec
from .conflicts import Conflict
from .continuation import Resolution, effective_paths, resolve
from .models import Book, CalendarAttachment, Event, LibraryCalendar, Plotline
from .ordering import Violation
from .plotline_health import CONFLICT, Finding, conflict_count, findings_for_path
from .reports import BookReport
from .scheduling import Window

# -- links -------------------------------------------------------------------


def _book_url(b: str) -> str:
    return f"/books/{b}"


def _plotline_url(b: str, p: str) -> str:
    return f"/books/{b}/plotlines/{p}"


def _calendar_url(owner: str, c: str) -> str:
    return f"/calendars/{owner}/{c}"


def _event_url(b: str, e: str) -> str:
    return f"/books/{b}/events/{e}"


# -- small pieces ------------------------------------------------------------


UNSCHEDULED = "unscheduled"


def _label(tick: int | None, codec: TimeCodec) -> str | None:
    return None if tick is None else codec.format(tick)


def _when(event: Event, codec: TimeCodec, span: bool = False) -> str:
    if not event.is_scheduled:
        return UNSCHEDULED
    start = codec.format(event.start_tick)
    if span and event.end_tick != event.start_tick:
        end = codec.format(event.end_tick)
        # Two different ticks can share a label -- a scene that begins and ends
        # before a reckoning was being kept reads "before X" at both ends. The
        # arrow between two identical strings says nothing except that something
        # is wrong with the renderer, so it is dropped.
        if end != start:
            return f"{start} → {end}"
    return start


def event_when(event: Event, codec: TimeCodec) -> str:
    """The human timeframe for one scene: 'unscheduled', a tick, or a span."""
    return _when(event, codec, span=True)


def _window(window: Window | None, codec: TimeCodec) -> dict | None:
    """The range an unscheduled scene must fall inside (design §4.2)."""
    if window is None or window.unconstrained:
        return None
    out = {
        "earliest": window.earliest,
        "latest": window.latest,
        "earliest_label": _label(window.earliest, codec),
        "latest_label": _label(window.latest, codec),
        "impossible": window.impossible,
    }
    if window.impossible:
        out.update(
            code="IMPOSSIBLE_WINDOW",
            message=(
                "The surrounding scenes leave no room for this one: it would have "
                f"to start after {window.earliest} and end before {window.latest}."
            ),
            doc="docs/chronos/design.md#42",
        )
    return out


def _node_ref(event: Event, codec: TimeCodec, span: bool = False, location: bool = False) -> dict:
    node = {"id": event.id, "title": event.display_title, "when": _when(event, codec, span)}
    if location:
        node["location"] = event.location.id
    return node


def _plotline_ref(pl: Plotline) -> dict:
    return {"id": pl.id, "title": pl.display_title}


def _ok() -> dict:
    return {"state": "ok"}


def _ordering_verdict(violation: Violation | None) -> dict:
    if violation is None:
        return _ok()
    return {
        "state": "conflicted",
        "code": "ORDERING_VIOLATION",
        "message": f"'{violation.before_id}' does not end before '{violation.after_id}' begins.",
        "evidence": {
            "before": violation.before_id,
            "after": violation.after_id,
            "reason": violation.reason,
        },
        "doc": "docs/chronos/design.md#52",
    }


def _terminus_verdict(last_event: str | None, terminus: str | None) -> dict:
    if terminus and last_event == terminus:
        return _ok()
    return {
        "state": "conflicted",
        "code": "TERMINUS_VIOLATION",
        "message": "Plotline does not end at the book's terminus.",
        "evidence": {"last_event": last_event, "terminus": terminus},
        "doc": "docs/chronos/design.md#53",
    }


def _span(events: list[Event], codec: TimeCodec) -> dict | None:
    scheduled = [e for e in events if e.is_scheduled]
    if not scheduled:
        return None
    start = min(e.start_tick for e in scheduled)
    end = max(e.end_tick for e in scheduled)
    return {
        "start_tick": start,
        "end_tick": end,
        "start_label": codec.format(start),
        "end_label": codec.format(end),
    }


def conflict_finding(c: Conflict, codec: TimeCodec) -> dict:
    return {
        "code": "TEMPORAL_CONFLICT",
        "message": (
            f"'{c.this_id}' and '{c.other_id}' place a character in two places at once."
        ),
        "evidence": {
            "events": [c.this_id, c.other_id],
            "characters": [ref.id for ref in c.characters],
            "locations": [c.this_location.id, c.other_location.id],
            "ticks": [list(c.this_ticks), list(c.other_ticks)],
        },
        "doc": "docs/chronos/design.md#51",
    }


# -- events ------------------------------------------------------------------


def present_event(public: dict, codec: TimeCodec, window: Window | None = None) -> dict:
    event = Event.from_storage(public)
    return {
        "kind": "event",
        "id": event.id,
        "book": public["book"],
        "title": event.title,
        "location": event.location.to_dict(),
        "start_tick": event.start_tick,
        "end_tick": event.end_tick,
        "start_label": _label(event.start_tick, codec),
        "end_label": _label(event.end_tick, codec),
        "scheduled": event.is_scheduled,
        "characters": [c.to_dict() for c in event.characters],
        "items": [i.to_dict() for i in event.items],
        "description": event.description,
        # Only meaningful while unscheduled: where its neighbours allow it to go.
        "window": None if event.is_scheduled else _window(window, codec),
        "rev": public["rev"],
        "_links": {
            "self": _event_url(public["book"], event.id),
            "book": _book_url(public["book"]),
            "plotlines": _event_url(public["book"], event.id) + "/plotlines",
        },
    }


def event_finding(finding: Finding) -> dict:
    """One per-scene finding, in the shared finding vocabulary (code/message/doc).

    ``severity`` separates a contradiction the writer should fix from a hint
    (``info``) they may ignore; ``events`` names the other scenes involved so a
    UI can link straight to them; ``refs`` names the Akasha articles the message
    quotes, so a UI can show their titles instead of their slugs.
    """
    out = {
        "code": finding.code,
        "severity": finding.severity,
        "message": finding.message,
        "events": list(finding.events),
        # The Akasha articles the message names, by id. A client holding the
        # article grant can resolve each to its title and substitute it into the
        # message; one that does not keeps the id, which is the correct outcome.
        "refs": [ref.to_dict() for ref in finding.refs],
    }
    if finding.doc:
        out["doc"] = finding.doc
    return out


def _event_summary(
    event: Event, codec: TimeCodec, shared_with: list[str],
    is_convergence: bool, is_divergence: bool, is_terminus: bool,
    owned: bool = True, findings: list[Finding] = (),
) -> dict:
    body = event.description
    preview = (body[:140] + "…") if len(body) > 140 else body
    return {
        "id": event.id,
        "title": event.display_title,
        "start_tick": event.start_tick,
        "end_tick": event.end_tick,
        "start_label": _label(event.start_tick, codec),
        "end_label": _label(event.end_tick, codec),
        # The label pre-split into coarse-to-fine components by the codec, so a UI
        # can group by year/month (or any fantasy cycle) without re-parsing the
        # string. Null when unscheduled.
        "start_parts": codec.parts(event.start_tick) if event.is_scheduled else None,
        "end_parts": codec.parts(event.end_tick) if event.is_scheduled else None,
        "scheduled": event.is_scheduled,
        "location": event.location.to_dict(),
        "characters": [c.to_dict() for c in event.characters],
        "items": [i.to_dict() for i in event.items],
        "description_preview": preview,
        "shared_with": shared_with,
        # Where this thread meets others: threads merge in (convergence) or split
        # off (divergence) here. The single-plotline timeline surfaces these so a
        # writer sees an interaction without opening the connected-plots view.
        "is_convergence": is_convergence,
        "is_divergence": is_divergence,
        "is_terminus": is_terminus,
        # Whether this scene sits in the plotline's *own* stored segment. A scene
        # inherited through ``continues_into`` belongs to the thread it is stored
        # on, so an editor must send the writer there rather than reorder it here.
        "owned": owned,
        # What is wrong (or merely worth knowing) about this scene on this thread.
        "findings": [event_finding(f) for f in findings],
    }


# -- plotlines ---------------------------------------------------------------


def _continuation_verdict(resolution: Resolution) -> dict:
    if resolution.cycle:
        return {
            "state": "conflicted", "code": "PLOTLINE_CYCLE",
            "message": "This plotline's continuation chain loops.",
            "evidence": {"cycle": resolution.cycle},
            "doc": "docs/chronos/design.md#33",
        }
    if resolution.missing:
        return {
            "state": "conflicted", "code": "INVALID_PLOTLINE",
            "message": f"Continues into '{resolution.missing}', which does not exist.",
            "evidence": {"missing": resolution.missing},
            "doc": "docs/chronos/design.md#33",
        }
    if resolution.anchor_missing:
        # Reachable without anyone writing this thread: dropping the joined-at
        # scene from the *target* strands the join. Reported rather than
        # repaired, because guessing a new join point would silently rewrite a
        # story -- either gaining the trunk's opening or losing a scene.
        return {
            "state": "conflicted", "code": "INVALID_PLOTLINE",
            "message": (
                f"Joins at '{resolution.anchor_missing}', which is no longer on the "
                "continuation's path."
            ),
            "evidence": {"anchor_missing": resolution.anchor_missing},
            "doc": "docs/chronos/design.md#33",
        }
    return _ok()


def _title_of(plotline_id: str | None, plotlines: list[Plotline]) -> str | None:
    """A plotline's display title from its id, or None if it names nothing."""
    if plotline_id is None:
        return None
    return next(
        (p.display_title for p in plotlines if p.id == plotline_id), None
    )


def present_plotline(
    public: dict,
    book: Book,
    plotlines: list[Plotline],
    events_by_id: dict[str, Event],
    codec: TimeCodec,
    expand: bool = False,
    missing_refs=(),
) -> dict:
    this = Plotline.from_storage(public)
    paths = effective_paths([*(p for p in plotlines if p.id != this.id), this])
    resolution = resolve(this.id, {p.id: p for p in plotlines} | {this.id: this})
    path = paths.get(this.id, list(this.events))

    ordered = [events_by_id[eid] for eid in path if eid in events_by_id]
    last_event = path[-1] if path else None
    graph = build_graph(paths)
    convergence = {n for n in graph if graph.in_degree(n) > 1}
    divergence = {n for n in graph if graph.out_degree(n) > 1}
    membership = {
        eid: sorted(pid for pid, evs in paths.items() if eid in evs and pid != this.id)
        for eid in path
    }

    # The same per-scene findings the editor marks up, computed once: their count
    # is part of every plotline's status, so a caller learns whether the thread
    # holds together without asking for the expanded path.
    findings = findings_for_path(path, events_by_id, paths, codec, missing_refs)

    if expand:
        # ``resolve`` concatenates this plotline's own segment first, so the
        # inherited tail is exactly the part of the path past its own length.
        own_length = len(this.events)
        events_field = [
            _event_summary(
                events_by_id[eid],
                codec,
                shared_with=membership.get(eid, []),
                is_convergence=eid in convergence,
                is_divergence=eid in divergence,
                is_terminus=eid == book.terminus,
                owned=index < own_length,
                findings=findings.get(eid, []),
            )
            for index, eid in enumerate(path)
            if eid in events_by_id
        ]
    else:
        events_field = list(path)

    return {
        "kind": "plotline",
        "id": this.id,
        "title": this.title,
        "overview": this.overview,
        "book": public["book"],
        "goals": this.goals,
        "events": list(this.events),
        "continues_into": this.continues_into,
        # The target's display title, alongside its id. Supplied because the
        # caller showing "continues into <x>" has the *id* and would otherwise
        # have to fetch the whole target to name it readably -- while this
        # presenter already holds every plotline in the book. Null when there is
        # no continuation, and when the target does not exist: a dangling
        # pointer is already reported by ``status.continuation``, and inventing
        # a title for it would dress the break up as working.
        "continues_into_title": _title_of(this.continues_into, plotlines),
        "continues_into_at": this.continues_into_at,
        "effective_events": events_field,
        "rev": public["rev"],
        "status": {
            "ordering": _ordering_verdict(_ordering_violation(ordered)),
            "ends_at_terminus": _terminus_verdict(last_event, book.terminus),
            "continuation": _continuation_verdict(resolution),
            "span": _span(ordered, codec),
            "conflicts": conflict_count(findings),
        },
        "_links": {
            "self": _plotline_url(public["book"], this.id),
            "book": _book_url(public["book"]),
            "expanded": _plotline_url(public["book"], this.id) + "?expand=events",
            "validate": _book_url(public["book"]) + "/validate",
            "graph": _book_url(public["book"]) + "/graph",
            "events": [_event_url(public["book"], eid) for eid in path],
        },
    }


def as_preview(plotline: dict, book_id: str) -> dict:
    """Re-label a presented plotline as the *candidate* it actually is.

    The preview runs a draft through ``present_plotline`` on purpose -- that is
    what guarantees the editor and a save cannot disagree. But the result must
    not then claim to be a stored plotline: it has no revision, and its id may
    name nothing at all. So the revision goes, ``self`` goes (it would 404), and
    ``kind`` says plainly what this is.
    """
    out = {k: v for k, v in plotline.items() if k not in ("rev", "_links")}
    out["kind"] = "plotline-preview"
    out["_links"] = {
        "book": _book_url(book_id),
        "validate": _book_url(book_id) + "/validate",
    }
    return out


def _ordering_violation(ordered: list[Event]) -> Violation | None:
    from .ordering import validate_order

    return validate_order(ordered)


# -- neighborhood (§7.4) -----------------------------------------------------


def _edge_groups(groups, events_by_id, plotlines_by_id, codec, key) -> list[dict]:
    out = []
    for g in groups:
        neighbor = events_by_id.get(g.node)
        node = _node_ref(neighbor, codec) if neighbor else {"id": g.node}
        out.append({key: node, "plotlines": [
            _plotline_ref(plotlines_by_id[p]) for p in g.plotlines if p in plotlines_by_id
        ]})
    return out


def _neighborhood_summary(n: Neighborhood) -> str:
    if n.is_terminus:
        return "The terminus — all plotlines end here."
    if n.role == "convergence+divergence":
        return "Threads both merge into and split out of this event."
    if n.is_convergence:
        return f"Convergence point: threads merge here from {len(n.incoming)} prior events."
    if n.is_divergence:
        return f"Divergence point: threads split here toward {len(n.outgoing)} events."
    if n.is_origin:
        return "A starting point (no prior event)."
    return f"{len(n.through)} plotline(s) pass through this event."


def present_neighborhood(
    n: Neighborhood,
    center: Event,
    events_by_id: dict[str, Event],
    plotlines_by_id: dict[str, Plotline],
    codec: TimeCodec,
    book_id: str,
) -> dict:
    return {
        "event": _node_ref(center, codec, span=True, location=True),
        "role": n.role,
        "summary": _neighborhood_summary(n),
        "through": [
            _plotline_ref(plotlines_by_id[p]) for p in n.through if p in plotlines_by_id
        ],
        "converging": {
            "is_convergence": n.is_convergence,
            "incoming": _edge_groups(n.incoming, events_by_id, plotlines_by_id, codec, "from"),
        },
        "diverging": {
            "is_divergence": n.is_divergence,
            "outgoing": _edge_groups(n.outgoing, events_by_id, plotlines_by_id, codec, "to"),
        },
        "is_terminus": n.is_terminus,
        "is_origin": n.is_origin,
        "_links": {
            "self": _event_url(book_id, center.id) + "/plotlines",
            "event": _event_url(book_id, center.id),
            "graph": _book_url(book_id) + "/graph",
        },
    }


# -- books & validate --------------------------------------------------------


def status_of(report: BookReport) -> str:
    return "consistent" if report.ok else "conflicted"


def present_attachment(attachment: CalendarAttachment, primary: bool) -> dict:
    """One of a book's reckonings, as the view switcher needs it.

    The descriptor rides along because it is the book's own copy: whoever can
    read the book can read its dates, with no second request and no grant on the
    library entry it was copied from.
    """
    return {
        "id": attachment.id,
        "label": attachment.display_label,
        "descriptor": attachment.descriptor,
        "from_tick": attachment.from_tick,
        "until_tick": attachment.until_tick,
        # Whether this is the one a read with no ``?calendar=`` uses.
        "primary": primary,
        # Where the copy came from, owner-qualified. Null once the writer edits
        # it into something of their own.
        "source": attachment.source,
    }


def present_book(public: dict, report: BookReport, plotline_ids: list[str]) -> dict:
    book = Book.from_storage(public)
    return {
        "kind": "book",
        "id": public["id"],
        "title": public.get("title"),
        "overview": public.get("overview", ""),
        "terminus": public.get("terminus"),
        # The single descriptor a pre-library client still expects: the primary
        # attachment's. Derived from the same list the new field presents, so the
        # two cannot drift.
        "calendar": book.calendar,
        "calendars": [
            present_attachment(c, primary=(index == 0))
            for index, c in enumerate(book.calendars)
        ],
        # Stored, so it is presented: a client is told to send the stored fields
        # back on a PUT, which it can only do for fields it was given.
        "world": public.get("world"),
        "plotlines": sorted(plotline_ids),
        "status": status_of(report),
        "rev": public["rev"],
        "_links": {
            "self": _book_url(public["id"]),
            "validate": _book_url(public["id"]) + "/validate",
            "graph": _book_url(public["id"]) + "/graph",
        },
    }


# -- the calendar library -----------------------------------------------------


def present_calendar(public: dict) -> dict:
    """One named, reusable calendar.

    Owner-qualified throughout, because ``(owner, id)`` is this resource's whole
    identity: two writers may each keep an ``imperial``, and a response that
    named only the slug would be ambiguous the moment one is shared.
    """
    calendar = LibraryCalendar.from_storage(public)
    owner = public["owner"]
    return {
        "kind": "calendar",
        "id": calendar.id,
        "owner": owner,
        # What a picker shows when the same slug appears twice: "alice/imperial"
        # for someone else's, the bare slug for your own. Computed here so every
        # surface qualifies it the same way.
        "qualified_id": f"{owner}/{calendar.id}",
        "name": calendar.name,
        "descriptor": calendar.descriptor,
        "notes": calendar.notes,
        "rev": public["rev"],
        "_links": {"self": _calendar_url(owner, calendar.id)},
    }


def present_ticks(ticks: list[int], codec: TimeCodec, readings=()) -> dict:
    """Translate raw ticks into what the book's calendars call them.

    A writer typing ``240`` into a timeframe field should not have to do
    mixed-radix arithmetic in their head to know that is Day 11. The codec is
    the only thing that knows -- and it only goes one way (``parse`` is
    deliberately unimplemented for fantasy calendars) -- so the browser asks
    rather than guessing.

    ``readings`` adds the *other* attached calendars, each labelling the same
    tick. That is the one place the feature demonstrates itself for free: at the
    moment a writer is choosing when a scene happens, they see it dated in every
    reckoning their book keeps, including the ones that were not being kept then.
    ``label``/``parts`` stay exactly what a single-calendar client always got.

    ``components`` is the same date as numbers rather than prose -- what a form
    puts *back into* its inputs, and what it would send to schedule this tick.
    ``null`` where there is no date to be had: a plain tick line, or a tick
    outside the era this reckoning was kept for.
    """
    return {
        "ticks": [
            {
                "tick": tick,
                "label": codec.format(tick),
                "parts": codec.parts(tick),
                "components": codec.components(tick),
                "readings": [
                    {
                        "calendar": attachment.id,
                        "name": attachment.display_label,
                        "label": reading.format(tick),
                    }
                    for attachment, reading in readings
                ],
            }
            for tick in ticks
        ]
    }


def present_dates(start: int | None, end: int | None, codec: TimeCodec, readings=()) -> dict:
    """What a pair of dates resolves to -- the scene form's live "= tick" echo.

    The inverse of ``present_ticks``, and deliberately shaped like it: the ticks
    the dates named, plus those ticks dated back again, so the form can show the
    reading it is about to save without a second round trip. Resolving here
    rather than in the browser keeps the calendar arithmetic in exactly one
    place; a client that disagreed with the server about what "Day 12" means
    would be the worst possible bug in this feature.
    """
    ticks = [t for t in (start, end) if t is not None]
    return {
        "start_tick": start,
        "end_tick": end,
        **present_ticks(ticks, codec, readings),
    }


def with_permissions(book: dict, write: bool, delete: bool) -> dict:
    """Tell the caller what it may do with this book, so a UI can decide what to
    offer before the writer clicks it.

    Authorization itself stays in the web layer (it needs the request's identity
    and the shared grant store); this only shapes the answer, keeping every
    response field defined in one place.
    """
    return {**book, "permissions": {"write": write, "delete": delete}}


def present_validate(report: BookReport, codec: TimeCodec) -> dict:
    return {
        "status": status_of(report),
        "temporal_conflicts": [conflict_finding(c, codec) for c in report.temporal_conflicts],
        "ordering": [
            {"plotline": i.plotline, **_ordering_verdict(i.violation)} for i in report.ordering
        ],
        "convergence": {
            "ok": report.convergence.ok if report.convergence else False,
            "terminus": report.convergence.terminus if report.convergence else None,
            "failures": report.convergence.failures if report.convergence else [],
        },
        # Articles a scene names that have since been deleted from Akasha.
        # Always something that went missing *underneath* a finished scene:
        # writes refuse an unknown reference, and nothing in Akasha knows to
        # warn a writer that a timeline points at what they are deleting.
        "missing_entities": [
            {"event": m.event, "role": m.role, "ref": m.ref.to_dict()}
            for m in report.missing_entities
        ],
        # A to-do list, not a fault: scenes still waiting for timing, each with
        # the window its neighbours imply.
        "unscheduled": [
            {"event": eid, "window": _window(window, codec)}
            for eid, window in sorted(report.unscheduled.items())
        ],
    }


# -- the book's continuity report ---------------------------------------------

# Every issue code, in the order the report reads, under the heading it is filed
# beneath. Two codes may share a heading (a continuation is broken the same way
# whether the chain loops or points at nothing), and the report merges them.
#
# The headings live here rather than in the browser for the same reason the
# finding messages do: one vocabulary, decided once, so the report and the
# plotline view cannot end up calling the same rule two different things.
_ISSUE_GROUPS = (
    ("TEMPORAL_CONFLICT", "A character in two places at once"),
    ("ORDERING_VIOLATION", "Scenes out of order"),
    ("IMPOSSIBLE_WINDOW", "Scenes with no room on the timeline"),
    ("MISSING_ENTITY", "Articles that are no longer there"),
    ("NO_TERMINUS", "No ending designated"),
    ("TERMINUS_VIOLATION", "Threads that do not reach the ending"),
    ("EMPTY_PLOTLINE", "Threads with no scenes"),
    ("UNSCHEDULED", "Scenes still waiting for a time"),
    ("PLOTLINE_CYCLE", "Broken continuations"),
    ("INVALID_PLOTLINE", "Broken continuations"),
)


def _scene_ref(event_id: str | None, events_by_id: dict[str, Event]) -> dict | None:
    if event_id is None:
        return None
    event = events_by_id.get(event_id)
    return {"id": event_id, "title": event.display_title if event else event_id}


def present_issue(issue: Issue, events_by_id: dict[str, Event], titles: dict) -> dict:
    """One issue in the book report.

    ``scene`` is what the message is said *about* -- findings are phrased from a
    scene's point of view, so the two are only legible together. ``plotlines``
    is every thread that can see it, which at book scale is the question a
    per-thread view never has to answer.
    """
    out = {
        "code": issue.code,
        "severity": issue.severity,
        "message": issue.message,
        "scene": _scene_ref(issue.scene, events_by_id),
        "events": [_scene_ref(e, events_by_id) for e in issue.events],
        "plotlines": [{"id": p, "title": titles.get(p, p)} for p in issue.plotlines],
        "refs": [ref.to_dict() for ref in issue.refs],
    }
    if issue.doc:
        out["doc"] = issue.doc
    return out


def _issue_groups(issues: list[Issue], events_by_id, titles) -> list[dict]:
    """Issues filed under their headings, in the fixed order above.

    Stable within a group, so the story order the report was built in survives.
    """
    rank = {code: i for i, (code, _) in enumerate(_ISSUE_GROUPS)}
    heading = dict(_ISSUE_GROUPS)
    groups: dict[str, dict] = {}
    for issue in sorted(issues, key=lambda i: rank.get(i.code, len(rank))):
        title = heading.get(issue.code, issue.code)
        # Uniform by construction -- severity follows the code, groups follow the
        # heading, and problems and notes are grouped separately -- so the group
        # can state it once instead of every row in it repeating the same mark.
        group = groups.setdefault(
            title, {"title": title, "severity": issue.severity, "codes": [], "issues": []}
        )
        if issue.code not in group["codes"]:
            group["codes"].append(issue.code)
        group["issues"].append(present_issue(issue, events_by_id, titles))
    return list(groups.values())


def _thread_rollup(problems: list[Issue], plotlines: list[Plotline]) -> list[dict]:
    """Every thread, with how many of this report's problems name it.

    A triage list -- which thread to open first -- and the filter's menu, in one
    answer. Deliberately **not** the same number as the plotline table's Health
    column: that counts contradictions among the scenes on a thread, while this
    also counts the whole-thread verdicts (never reaching the ending, no scenes
    at all) which the table has never shown. Two questions, so the report labels
    its column for the one it is answering rather than inviting the comparison.
    """
    counted: dict[str, int] = {}
    for issue in problems:
        for plotline_id in issue.plotlines:
            counted[plotline_id] = counted.get(plotline_id, 0) + 1
    return [{**_plotline_ref(p), "problems": counted.get(p.id, 0)} for p in plotlines]


def present_book_report(
    issues: list[Issue], events_by_id: dict[str, Event], plotlines: list[Plotline]
) -> dict:
    """The whole book's continuity report, grouped and counted for reading.

    Two sections rather than one list. ``problems`` are the contradictions --
    exactly the categories a book's ``status`` is computed from, so a book this
    calls conflicted is a book whose card says ``conflicted``. ``notes`` are
    things worth knowing that are not faults: a scene still waiting for a time is
    a draft state, and saying otherwise would leave every book in progress red.
    """
    titles = {p.id: p.display_title for p in plotlines}
    problems = [i for i in issues if i.severity == CONFLICT]
    notes = [i for i in issues if i.severity != CONFLICT]
    return {
        "status": "conflicted" if problems else "consistent",
        "summary": {
            "problems": len(problems),
            "notes": len(notes),
            # Counted apart from the other notes: it is the one a writer works
            # down as a to-do list, and the report's headline says how long it is.
            "unscheduled": sum(1 for i in notes if i.code == "UNSCHEDULED"),
        },
        "problems": _issue_groups(problems, events_by_id, titles),
        "notes": _issue_groups(notes, events_by_id, titles),
        # Every thread in the book and its share of the problems, so the report
        # can be triaged and narrowed to one without a second request.
        "plotlines": _thread_rollup(problems, plotlines),
    }


def present_graph(
    view: dict,
    events_by_id: dict[str, Event],
    plotlines_by_id: dict[str, Plotline],
    codec: TimeCodec,
) -> dict:
    """The whole story graph, enriched so a client can lay it out by tick and
    colour it by role in a single call (design §7.4, §12).

    Each node carries its timing (ticks + codec labels) and its role flags
    (convergence/divergence/terminus). The ``plotlines`` block gives one lane per
    thread: its title, its **stored** own segment (``events``) and its
    ``continues_into`` alongside the **resolved** ``effective_events`` -- keeping
    stored-vs-inherited provenance recoverable so a future editor can route an
    edit back to the right stored field, not the flattened path.
    """
    convergence = set(view["convergence"])
    divergence = set(view["divergence"])
    terminus = view["terminus"]

    def node(eid: str) -> dict:
        e = events_by_id.get(eid)
        return {
            "id": eid,
            "title": e.display_title if e else None,
            "start_tick": e.start_tick if e else None,
            "end_tick": e.end_tick if e else None,
            "start_label": _label(e.start_tick, codec) if e else None,
            "end_label": _label(e.end_tick, codec) if e else None,
            # Coarse-to-fine label components, so a client groups by year/month
            # (the same way the single-plotline timeline does) without re-parsing
            # the string. Null when unscheduled.
            "start_parts": codec.parts(e.start_tick) if (e and e.is_scheduled) else None,
            "end_parts": codec.parts(e.end_tick) if (e and e.is_scheduled) else None,
            "scheduled": e.is_scheduled if e else False,
            "is_convergence": eid in convergence,
            "is_divergence": eid in divergence,
            "is_terminus": eid == terminus,
        }

    def lane(pid: str, effective: list[str]) -> dict:
        pl = plotlines_by_id.get(pid)
        return {
            "id": pid,
            "title": pl.display_title if pl else pid,
            "events": list(pl.events) if pl else list(effective),
            "continues_into": pl.continues_into if pl else None,
            "continues_into_at": pl.continues_into_at if pl else None,
            "effective_events": list(effective),
        }

    return {
        "nodes": [node(eid) for eid in view["nodes"]],
        "edges": view["edges"],
        "convergence": view["convergence"],
        "divergence": view["divergence"],
        "terminus": terminus,
        "plotlines": [lane(pid, view["paths"][pid]) for pid in sorted(view["paths"])],
    }
