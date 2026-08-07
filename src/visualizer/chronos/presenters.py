"""Response shaping (design §6.4, §7.2, §7.4, §7.6) -- the single source of
every response dict.

Keeping this in one pure-ish place (it depends only on models + codec, never on
Flask or Mongo) means the code, the OpenAPI schema, and the examples all trace
to one definition. It turns ids into titles, ticks into codec labels, and adds
`_links` / `status` so responses explain themselves.
"""

from .book_rules import Neighborhood, build_graph
from .calendar import TimeCodec
from .conflicts import Conflict
from .continuation import Resolution, effective_paths, resolve
from .models import Book, Event, Plotline
from .ordering import Violation
from .plotline_health import Finding, conflict_count, findings_for_path
from .reports import BookReport
from .scheduling import Window

_SCHEMA = "/openapi.json#/components/schemas"


# -- links -------------------------------------------------------------------


def _book_url(b: str) -> str:
    return f"/books/{b}"


def _plotline_url(b: str, p: str) -> str:
    return f"/books/{b}/plotlines/{p}"


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
        return f"{start} → {codec.format(event.end_tick)}"
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
    return _ok()


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
        "book": public["book"],
        "goals": this.goals,
        "events": list(this.events),
        "continues_into": this.continues_into,
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
        "_schema": f"{_SCHEMA}/Plotline",
    }


def as_preview(plotline: dict, book_id: str) -> dict:
    """Re-label a presented plotline as the *candidate* it actually is.

    The preview runs a draft through ``present_plotline`` on purpose -- that is
    what guarantees the editor and a save cannot disagree. But the result must
    not then claim to be a stored plotline: it has no revision, and its id may
    name nothing at all. So the revision goes, ``self`` goes (it would 404), and
    ``kind`` says plainly what this is.
    """
    out = {k: v for k, v in plotline.items() if k not in ("rev", "_links", "_schema")}
    out["kind"] = "plotline-preview"
    out["_links"] = {
        "book": _book_url(book_id),
        "validate": _book_url(book_id) + "/validate",
    }
    out["_schema"] = f"{_SCHEMA}/PlotlinePreviewResult"
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


def present_book(public: dict, report: BookReport, plotline_ids: list[str]) -> dict:
    return {
        "kind": "book",
        "id": public["id"],
        "title": public.get("title"),
        "terminus": public.get("terminus"),
        "calendar": public.get("calendar"),
        "plotlines": sorted(plotline_ids),
        "status": status_of(report),
        "rev": public["rev"],
        "_links": {
            "self": _book_url(public["id"]),
            "validate": _book_url(public["id"]) + "/validate",
            "graph": _book_url(public["id"]) + "/graph",
        },
    }


def present_ticks(ticks: list[int], codec: TimeCodec) -> dict:
    """Translate raw ticks into what the book's calendar calls them.

    A writer typing ``240`` into a timeframe field should not have to do
    mixed-radix arithmetic in their head to know that is Day 11. The codec is
    the only thing that knows -- and it only goes one way (``parse`` is
    deliberately unimplemented for fantasy calendars) -- so the browser asks
    rather than guessing.
    """
    return {
        "ticks": [
            {"tick": tick, "label": codec.format(tick), "parts": codec.parts(tick)}
            for tick in ticks
        ]
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
