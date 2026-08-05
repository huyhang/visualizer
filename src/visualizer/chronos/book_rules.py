"""Book-level graph rules (design §5.3, §7.4) -- pure, no I/O.

The story graph is the union of every plotline's ordering: events are nodes,
each consecutive pair is an edge carrying the plotline id(s) that traverse it.
Rules here operate on **effective paths** (``{plotline_id: [event_id, ...]}``,
produced by ``continuation.effective_paths``) rather than on ``Plotline``
objects, so a thread stored as a segment plus a continuation is indistinguishable
from one written out in full.
Convergence (in-degree > 1) and divergence (out-degree > 1) fall out of the
graph, and acyclicity is free because ticks strictly increase along edges. Built
with NetworkX per the design; book graphs are tiny, so this is cheap.
"""

from dataclasses import dataclass, field
from itertools import pairwise

import networkx as nx

# -- convergence / terminus (§5.3) -------------------------------------------


@dataclass
class ConvergenceReport:
    ok: bool
    terminus: str | None
    failures: list[dict] = field(default_factory=list)


def validate_convergence(paths: dict[str, list[str]], terminus_id: str | None) -> ConvergenceReport:
    """Every plotline's *effective* path must be non-empty and end at the terminus.

    A thread that continues into another satisfies this when the chain it joins
    eventually reaches the terminus -- the shared ending is only written once.
    Vacuously satisfied when a book has no plotlines yet.
    """
    if not paths:
        return ConvergenceReport(ok=True, terminus=terminus_id, failures=[])
    failures: list[dict] = []
    if not terminus_id:
        failures.append({"reason": "no terminus designated"})
        return ConvergenceReport(ok=False, terminus=terminus_id, failures=failures)
    for pid in sorted(paths):
        events = paths[pid]
        if not events:
            failures.append({"plotline": pid, "reason": "empty plotline"})
        elif events[-1] != terminus_id:
            failures.append(
                {"plotline": pid, "reason": "does not end at terminus",
                 "last_event": events[-1]}
            )
    return ConvergenceReport(ok=not failures, terminus=terminus_id, failures=failures)


# -- the story graph (§7.4) --------------------------------------------------


def build_graph(paths: dict[str, list[str]]) -> nx.DiGraph:
    """Union of all effective paths; edges carry the set of plotline ids.

    Because paths are resolved, the junction between a thread and the
    continuation it joins appears as a normal edge.
    """
    graph = nx.DiGraph()
    for pid, events in paths.items():
        graph.add_nodes_from(events)
        for a, b in pairwise(events):
            if graph.has_edge(a, b):
                graph[a][b]["plotlines"].add(pid)
            else:
                graph.add_edge(a, b, plotlines={pid})
    return graph


def is_acyclic(graph: nx.DiGraph) -> bool:
    return nx.is_directed_acyclic_graph(graph)


def _sorted_plotlines(edge_data: dict) -> list[str]:
    return sorted(edge_data["plotlines"])


@dataclass
class EdgeGroup:
    node: str
    plotlines: list[str]


@dataclass
class Neighborhood:
    event: str
    through: list[str]
    incoming: list[EdgeGroup]
    outgoing: list[EdgeGroup]
    is_convergence: bool
    is_divergence: bool
    is_terminus: bool
    is_origin: bool
    role: str


def _role(is_terminus: bool, is_origin: bool, conv: bool, div: bool) -> str:
    if is_terminus:
        return "terminus"
    if conv and div:
        return "convergence+divergence"
    if conv:
        return "convergence"
    if div:
        return "divergence"
    if is_origin:
        return "origin"
    return "interior"


def neighborhood(
    paths: dict[str, list[str]], event_id: str, terminus_id: str | None
) -> Neighborhood:
    """The event-local slice of the story graph (design §7.4)."""
    graph = build_graph(paths)
    through = sorted(pid for pid, events in paths.items() if event_id in events)
    incoming = [
        EdgeGroup(pred, _sorted_plotlines(graph[pred][event_id]))
        for pred in graph.predecessors(event_id)
    ] if event_id in graph else []
    outgoing = [
        EdgeGroup(succ, _sorted_plotlines(graph[event_id][succ]))
        for succ in graph.successors(event_id)
    ] if event_id in graph else []
    is_convergence = len(incoming) > 1
    is_divergence = len(outgoing) > 1
    is_terminus = event_id == terminus_id
    is_origin = len(incoming) == 0
    return Neighborhood(
        event=event_id,
        through=through,
        incoming=incoming,
        outgoing=outgoing,
        is_convergence=is_convergence,
        is_divergence=is_divergence,
        is_terminus=is_terminus,
        is_origin=is_origin,
        role=_role(is_terminus, is_origin, is_convergence, is_divergence),
    )


def graph_view(paths: dict[str, list[str]], terminus_id: str | None) -> dict:
    """The whole book's story graph, for the ``/graph`` endpoint."""
    graph = build_graph(paths)
    edges = [
        {"from": a, "to": b, "plotlines": _sorted_plotlines(data)}
        for a, b, data in graph.edges(data=True)
    ]
    convergence = sorted(n for n in graph if graph.in_degree(n) > 1)
    divergence = sorted(n for n in graph if graph.out_degree(n) > 1)
    return {
        "nodes": sorted(graph.nodes),
        "edges": edges,
        "convergence": convergence,
        "divergence": divergence,
        "terminus": terminus_id,
        # The resolved path of each plotline, so a client can draw one lane per
        # thread (order preserved) without re-deriving it from the edges.
        "paths": {pid: list(events) for pid, events in paths.items()},
    }
