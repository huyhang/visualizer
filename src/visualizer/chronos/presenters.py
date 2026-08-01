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


def _event_summary(
    event: Event, codec: TimeCodec, shared_with: list[str], is_convergence: bool, is_terminus: bool
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
        "scheduled": event.is_scheduled,
        "location": event.location.to_dict(),
        "characters": [c.to_dict() for c in event.characters],
        "items": [i.to_dict() for i in event.items],
        "description_preview": preview,
        "shared_with": shared_with,
        "is_convergence": is_convergence,
        "is_terminus": is_terminus,
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
) -> dict:
    this = Plotline.from_storage(public)
    paths = effective_paths([*(p for p in plotlines if p.id != this.id), this])
    resolution = resolve(this.id, {p.id: p for p in plotlines} | {this.id: this})
    path = paths.get(this.id, list(this.events))

    ordered = [events_by_id[eid] for eid in path if eid in events_by_id]
    last_event = path[-1] if path else None
    graph = build_graph(paths)
    convergence = {n for n in graph if graph.in_degree(n) > 1}
    membership = {
        eid: sorted(pid for pid, evs in paths.items() if eid in evs and pid != this.id)
        for eid in path
    }

    if expand:
        events_field = [
            _event_summary(
                events_by_id[eid],
                codec,
                shared_with=membership.get(eid, []),
                is_convergence=eid in convergence,
                is_terminus=eid == book.terminus,
            )
            for eid in path
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
        # A to-do list, not a fault: scenes still waiting for timing, each with
        # the window its neighbours imply.
        "unscheduled": [
            {"event": eid, "window": _window(window, codec)}
            for eid, window in sorted(report.unscheduled.items())
        ],
    }


def present_graph(view: dict, events_by_id: dict[str, Event]) -> dict:
    def title(eid: str) -> str | None:
        e = events_by_id.get(eid)
        return e.display_title if e else None

    return {
        "nodes": [{"id": eid, "title": title(eid)} for eid in view["nodes"]],
        "edges": view["edges"],
        "convergence": view["convergence"],
        "divergence": view["divergence"],
        "terminus": view["terminus"],
    }
