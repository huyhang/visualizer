// Which threads are on the map. Ported from the classic page's subgraph.js:
// the book's story graph in, a smaller graph of the same shape out, so the same
// layout draws a slice or the whole book.
//
// "Connected" means sharing at least one scene with the focus *other than the
// terminus*: every thread must end there, so counting it would make every
// thread connected and collapse that preset into the whole map. With no
// terminus yet, any shared scene connects.

import type { GoalRef, Graph, GraphEdge, GraphNode, GraphPlotline } from "../../api/types";

/** A drawn node: a scene, or a folded band standing for a run of them (see collapse.ts). */
export interface MapNode extends GraphNode {
  is_band?: boolean;
  events?: string[];
  lane_title?: string;
}

export interface Slice {
  nodes: MapNode[];
  edges: GraphEdge[];
  plotlines: GraphPlotline[];
  terminus: string | null;
  /** The thread the writer arrived from, emphasised but not required to be shown. */
  focus: string | null;
  goals?: GoalRef[];
}

/** Narrow `graph` to `ids`, dropping every thread, node and edge that no longer belongs. */
export function restrictTo(
  graph: Graph,
  ids: Iterable<string>,
  focus: string | null = null,
): Slice {
  const included = new Set(ids);
  const lanes = graph.plotlines.filter((p) => included.has(p.id));
  const nodeIds = new Set(lanes.flatMap((p) => p.effective_events));
  const nodes = graph.nodes.filter((n) => nodeIds.has(n.id));
  // Both endpoints have to survive, not only the tag: an edge tagged with a kept
  // thread but reaching a dropped scene would dangle.
  const edges = graph.edges
    .filter(
      (e) =>
        nodeIds.has(e.from) &&
        nodeIds.has(e.to) &&
        e.plotlines.some((p) => included.has(p)),
    )
    .map((e) => ({ ...e, plotlines: e.plotlines.filter((p) => included.has(p)) }));
  const terminus = graph.terminus && nodeIds.has(graph.terminus) ? graph.terminus : null;
  return { nodes, edges, plotlines: lanes, terminus, focus, goals: graph.goals };
}

/** The focus thread plus every thread meeting it somewhere other than the ending. */
export function connectedIds(
  graph: Pick<Graph, "plotlines" | "terminus">,
  focusId: string,
): Set<string> {
  const focus = graph.plotlines.find((p) => p.id === focusId);
  if (!focus) return new Set();
  const focusEvents = new Set(focus.effective_events);
  const meets = (lane: GraphPlotline) =>
    lane.effective_events.some((e) => e !== graph.terminus && focusEvents.has(e));
  return new Set([
    focusId,
    ...graph.plotlines.filter((l) => l.id !== focusId && meets(l)).map((l) => l.id),
  ]);
}

export function connectedTo(graph: Graph, focusId: string): Slice {
  return restrictTo(graph, connectedIds(graph, focusId), focusId);
}
