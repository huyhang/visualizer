// The git-graph layout: a slice in, positions out. Ported from the classic
// page's layout.js. No DOM, no SVG.
//
// Threads run top-to-bottom in time. Each thread owns a column; every scene is
// one node on one row, drawn in the leftmost column holding it, so a shared
// scene sits once and the other threads' edges curve into it -- that curve *is*
// the merge or the split.
//
// Injected rather than fixed, because the map varies them and tests drive them:
// `colorOf`/`dashOf` (book-wide, so a thread keeps its paint whatever else is
// shown) and `heightOf` (a row opened in place pushes everything below it down).

import { paletteColor, paletteDash } from "../threadColors";
import { orderLanes } from "./lanes";
import type { Slice } from "./subgraph";
import { rowByNode } from "./timeOrder";

export const geometry = {
  /** Horizontal gap between columns. */
  COL_W: 34,
  ROW_H: 58,
  ROW_COMPACT: 34,
  PAD_X: 22,
  PAD_TOP: 26,
  NODE_R: 7,
  /** Vertical room a period heading takes. */
  HEADER_H: 30,
  /** The narrowest the titles may be squeezed before the pane scrolls instead. */
  TEXT_MIN: 420,
} as const;

export interface LaneMeta {
  id: string;
  title: string;
  index: number;
  color: string;
  dash: string;
  isFocus: boolean;
  /** Where it lands once empty columns close up; null when it owns none. */
  column: number | null;
  x: number | null;
}

export interface LaidNode {
  id: string;
  title: string;
  row: number;
  x: number;
  y: number;
  lane: number;
  column: number;
  color: string;
  dash: string;
  isFocus: boolean;
  scheduled: boolean;
  startLabel: string | null;
  endLabel: string | null;
  startParts: string[] | null;
  endParts: string[] | null;
  startTick: number | null;
  endTick: number | null;
  isBand: boolean;
  events: string[] | null;
  laneTitle: string | null;
  isConvergence: boolean;
  isDivergence: boolean;
  isTerminus: boolean;
}

export interface LaidEdge {
  from: string;
  to: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color: string;
  dash: string;
  isFocus: boolean;
  plotlines: string[];
}

export interface Layout {
  width: number;
  minWidth: number;
  height: number;
  lanes: LaneMeta[];
  nodes: LaidNode[];
  edges: LaidEdge[];
  focus: string | null;
  hasUnscheduled: boolean;
}

export interface LayoutOptions {
  colorOf?: (id: string) => string;
  dashOf?: (id: string) => string;
  heightOf?: (node: { id: string }) => number;
}

/** The leftmost lane holding each node: the others branch to and from it. */
function laneByNode(nodeIds: Set<string>, lanes: Slice["plotlines"]): Map<string, number> {
  const lane = new Map<string, number>();
  lanes.forEach((p, i) => {
    for (const id of p.effective_events)
      if (nodeIds.has(id) && !lane.has(id)) lane.set(id, i);
  });
  for (const id of nodeIds) if (!lane.has(id)) lane.set(id, 0);
  return lane;
}

/**
 * Columns for the lanes that hold something, order preserved. A thread whose
 * every scene sits on an earlier one -- a trunk the others continue into --
 * gets no seat: reserving one was blank gutter and a resize with nothing behind it.
 */
function seats(lane: Map<string, number>): Map<number, number> {
  const used = [...new Set(lane.values())].sort((a, b) => a - b);
  return new Map(used.map((laneIdx, column) => [laneIdx, column]));
}

function degrees(edges: Slice["edges"]) {
  const indeg = new Map<string, number>();
  const outdeg = new Map<string, number>();
  for (const e of edges) {
    outdeg.set(e.from, (outdeg.get(e.from) ?? 0) + 1);
    indeg.set(e.to, (indeg.get(e.to) ?? 0) + 1);
  }
  return { indeg, outdeg };
}

/** Stack rows of varying height, centring each in the space it takes. */
export function stackRows(
  ordered: { id: string }[],
  heightOf: (n: { id: string }) => number,
  startY: number,
) {
  const centre = new Map<string, number>();
  let y = startY;
  for (const n of ordered) {
    const h = heightOf(n);
    centre.set(n.id, y + h / 2);
    y += h;
  }
  return { centre, bottom: y };
}

export function layoutGraph(slice: Slice, opts: LayoutOptions = {}): Layout {
  const lanes = orderLanes(slice.plotlines, { terminus: slice.terminus });
  const focusIndex = lanes.findIndex((p) => p.id === slice.focus);
  const indexOf = (id: string) => lanes.findIndex((p) => p.id === id);
  const colorOf = opts.colorOf ?? ((id: string) => paletteColor(indexOf(id)));
  const dashOf = opts.dashOf ?? ((id: string) => paletteDash(indexOf(id)));
  const heightOf = opts.heightOf ?? (() => geometry.ROW_H);

  const nodeIds = new Set(slice.nodes.map((n) => n.id));
  const row = rowByNode(slice.nodes, slice.edges);
  // Two numbers, and conflating them costs a thread its colour: `lane` is which
  // thread a node is drawn on (identity), `column` is where that lands (geometry).
  const lane = laneByNode(nodeIds, lanes);
  const seat = seats(lane);
  const { indeg, outdeg } = degrees(slice.edges);
  const laneOf = (id: string) => lane.get(id) ?? 0;
  const columnOf = (id: string) => seat.get(laneOf(id)) ?? 0;
  const xOf = (id: string) => geometry.PAD_X + columnOf(id) * geometry.COL_W;

  const laneMeta: LaneMeta[] = lanes.map((p, i) => {
    const column = seat.get(i) ?? null;
    return {
      id: p.id,
      title: p.title || p.id,
      index: i,
      color: colorOf(p.id),
      dash: dashOf(p.id),
      isFocus: i === focusIndex,
      column,
      x: column === null ? null : geometry.PAD_X + column * geometry.COL_W,
    };
  });
  const metaOf = (id: string) => laneMeta[laneOf(id)];

  const nodes: LaidNode[] = slice.nodes.map((n) => ({
    id: n.id,
    title: n.title || n.id,
    row: row.get(n.id) ?? 0,
    x: xOf(n.id),
    y: 0,
    lane: laneOf(n.id),
    column: columnOf(n.id),
    color: metaOf(n.id)?.color ?? paletteColor(0),
    dash: metaOf(n.id)?.dash ?? "",
    isFocus: laneOf(n.id) === focusIndex,
    scheduled: Boolean(n.scheduled),
    startLabel: n.start_label ?? null,
    endLabel: n.end_label ?? null,
    startParts: n.start_parts ?? null,
    endParts: n.end_parts ?? null,
    startTick: n.start_tick ?? null,
    endTick: n.end_tick ?? null,
    isBand: Boolean(n.is_band),
    events: n.events ?? null,
    laneTitle: n.lane_title ?? null,
    // Recomputed from *this* slice's edges, so a node that merges only in the
    // wider book reads honestly once those threads are hidden.
    isConvergence: (indeg.get(n.id) ?? 0) > 1,
    isDivergence: (outdeg.get(n.id) ?? 0) > 1,
    isTerminus: n.id === slice.terminus,
  }));

  const ordered = [...nodes].sort((a, b) => a.row - b.row);
  const { centre, bottom } = stackRows(ordered, heightOf, geometry.PAD_TOP);
  nodes.forEach((n) => (n.y = centre.get(n.id) ?? 0));

  // An edge wears its branch lane's paint (the higher-indexed end), so a thread
  // leaving or joining another is drawn in its own colour.
  const edges: LaidEdge[] = slice.edges.map((e) => {
    const branch = laneMeta[Math.max(laneOf(e.from), laneOf(e.to))];
    return {
      from: e.from,
      to: e.to,
      x1: xOf(e.from),
      y1: centre.get(e.from) ?? 0,
      x2: xOf(e.to),
      y2: centre.get(e.to) ?? 0,
      color: branch?.color ?? paletteColor(0),
      dash: branch?.dash ?? "",
      isFocus: branch?.index === focusIndex,
      plotlines: e.plotlines,
    };
  });

  const width = geometry.PAD_X + Math.max(1, seat.size) * geometry.COL_W;
  return {
    width,
    minWidth: width + 12 + geometry.TEXT_MIN,
    height: bottom,
    lanes: laneMeta,
    nodes,
    edges,
    focus: slice.focus,
    hasUnscheduled: nodes.some((n) => !n.scheduled),
  };
}
