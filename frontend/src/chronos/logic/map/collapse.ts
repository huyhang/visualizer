// How dense the map is drawn. Ported from the classic page's collapse.js: fold
// the stretches a thread walks *alone* into one band, and leave every junction
// standing. A slice in, a smaller slice of the same shape out, so the layout
// never learns anything was folded.
//
// A map is read for where threads meet; a scene only one thread passes through
// reads better on that thread's own timeline. A node is a junction when it is
// the terminus, when more than one shown thread holds it, or when it splits or
// joins within this slice -- so a scene that was a junction only because of a
// hidden thread folds like any other.

import type { GraphEdge, GraphPlotline } from "../../api/types";
import type { MapNode, Slice } from "./subgraph";

export const MIN_RUN = 3;

export interface Band {
  id: string;
  lane: string;
  events: string[];
}

export interface Dense extends Slice {
  /** Every run found, folded or not, so "Unfold all" needs no second pass. */
  bands: Band[];
}

/** Stable across redraws: the set of unfolded bands is keyed by it. */
export const bandId = (laneId: string, firstEventId: string) =>
  `~run:${laneId}:${firstEventId}`;

function junctionTest(slice: Slice): (id: string) => boolean {
  const laneCount = new Map<string, number>();
  for (const p of slice.plotlines) {
    for (const e of new Set(p.effective_events))
      laneCount.set(e, (laneCount.get(e) ?? 0) + 1);
  }
  const indeg = new Map<string, number>();
  const outdeg = new Map<string, number>();
  for (const e of slice.edges) {
    outdeg.set(e.from, (outdeg.get(e.from) ?? 0) + 1);
    indeg.set(e.to, (indeg.get(e.to) ?? 0) + 1);
  }
  return (id) =>
    id === slice.terminus ||
    (laneCount.get(id) ?? 0) > 1 ||
    (indeg.get(id) ?? 0) > 1 ||
    (outdeg.get(id) ?? 0) > 1;
}

/** Maximal runs of consecutive solo scenes along one thread's path. */
export function runsOf(
  lane: GraphPlotline,
  isJunction: (id: string) => boolean,
): string[][] {
  const runs: string[][] = [];
  let current: string[] = [];
  for (const id of lane.effective_events) {
    if (isJunction(id)) {
      if (current.length) runs.push(current);
      current = [];
    } else current.push(id);
  }
  if (current.length) runs.push(current);
  return runs;
}

/** A band carries its stretch's timing, so it sorts and groups where its scenes would have. */
function bandNode(
  id: string,
  lane: GraphPlotline,
  events: string[],
  byId: Map<string, MapNode>,
): MapNode {
  const dated = events
    .map((e) => byId.get(e))
    .filter((n): n is MapNode => Boolean(n?.scheduled));
  const first = dated[0] ?? null;
  const last = dated[dated.length - 1] ?? null;
  const name = lane.title || lane.id;
  return {
    id,
    is_band: true,
    events: [...events],
    lane_title: name,
    title: `${events.length} scenes on ${name}`,
    scheduled: Boolean(first),
    start_tick: first?.start_tick ?? null,
    end_tick: last?.end_tick ?? null,
    start_label: first?.start_label ?? null,
    end_label: last?.end_label ?? null,
    start_parts: first?.start_parts ?? null,
    end_parts: last?.end_parts ?? null,
    is_convergence: false,
    is_divergence: false,
    is_terminus: false,
  };
}

/** Rewire edges onto bands: in enters, out leaves, wholly inside disappears. */
function rewire(edges: GraphEdge[], at: (id: string) => string): GraphEdge[] {
  const out: GraphEdge[] = [];
  const seen = new Set<string>();
  for (const e of edges) {
    const from = at(e.from);
    const to = at(e.to);
    const key = `${from} ${to}`;
    if (from === to || seen.has(key)) continue;
    seen.add(key);
    out.push({ ...e, from, to });
  }
  return out;
}

export function collapseRuns(
  slice: Slice,
  {
    expanded = new Set<string>(),
    minRun = MIN_RUN,
  }: { expanded?: Set<string>; minRun?: number } = {},
): Dense {
  const isJunction = junctionTest(slice);
  const byId = new Map(slice.nodes.map((n) => [n.id, n]));
  const bands: Band[] = [];
  const folded = new Map<string, string>();
  const bandNodes: MapNode[] = [];

  for (const lane of slice.plotlines) {
    for (const run of runsOf(lane, isJunction)) {
      if (run.length < minRun) continue;
      const id = bandId(lane.id, run[0] ?? "");
      bands.push({ id, lane: lane.id, events: [...run] });
      if (expanded.has(id)) continue;
      run.forEach((e) => folded.set(e, id));
      bandNodes.push(bandNode(id, lane, run, byId));
    }
  }
  if (!bandNodes.length) return { ...slice, bands };

  const at = (id: string) => folded.get(id) ?? id;
  const plotlines = slice.plotlines.map((p) => ({
    ...p,
    effective_events: [...new Set(p.effective_events.map(at))],
  }));
  return {
    ...slice,
    nodes: slice.nodes.filter((n) => !folded.has(n.id)).concat(bandNodes),
    edges: rewire(slice.edges, at),
    plotlines,
    bands,
  };
}
