"""Book-level graph rules (design §5.3, §7.4) -- pure, no I/O.

The story graph is the union of every plotline's ordering: events are nodes,
each consecutive pair is an edge carrying the plotline id(s) that traverse it.
Convergence (in-degree > 1) and divergence (out-degree > 1) fall out of the
graph, and acyclicity is free because ticks strictly increase along edges. Built
with NetworkX per the design; book graphs are tiny, so this is cheap.
"""

from dataclasses import dataclass, field

import networkx as nx

from .models import Plotline

# -- convergence / terminus (§5.3) -------------------------------------------


@dataclass
class ConvergenceReport:
    ok: bool
    terminus: str | None
    failures: list[dict] = field(default_factory=list)


def validate_convergence(plotlines: list[Plotline], terminus_id: str | None) -> ConvergenceReport:
    """Every plotline must be non-empty and end at the terminus.

    Vacuously satisfied when a book has no plotlines yet (a fresh book is
    consistent until it has threads that need to converge).
    """
    if not plotlines:
        return ConvergenceReport(ok=True, terminus=terminus_id, failures=[])
    failures: list[dict] = []
    if not terminus_id:
        failures.append({"reason": "no terminus designated"})
        return ConvergenceReport(ok=False, terminus=terminus_id, failures=failures)
    for pl in plotlines:
        if not pl.events:
            failures.append({"plotline": pl.id, "reason": "empty plotline"})
        elif pl.events[-1] != terminus_id:
            failures.append(
                {"plotline": pl.id, "reason": "does not end at terminus",
                 "last_event": pl.events[-1]}
            )
    return ConvergenceReport(ok=not failures, terminus=terminus_id, failures=failures)


# -- the story graph (§7.4) --------------------------------------------------


def build_graph(plotlines: list[Plotline]) -> nx.DiGraph:
    """Union of all plotline orderings; edges carry the set of plotline ids."""
    graph = nx.DiGraph()
    for pl in plotlines:
        graph.add_nodes_from(pl.events)
        for a, b in zip(pl.events, pl.events[1:]):
            if graph.has_edge(a, b):
                graph[a][b]["plotlines"].add(pl.id)
            else:
                graph.add_edge(a, b, plotlines={pl.id})
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
    plotlines: list[Plotline], event_id: str, terminus_id: str | None
) -> Neighborhood:
    """The event-local slice of the story graph (design §7.4)."""
    graph = build_graph(plotlines)
    through = sorted(pl.id for pl in plotlines if event_id in pl.events)
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


def graph_view(plotlines: list[Plotline], terminus_id: str | None) -> dict:
    """The whole book's story graph, for the ``/graph`` endpoint."""
    graph = build_graph(plotlines)
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
    }
