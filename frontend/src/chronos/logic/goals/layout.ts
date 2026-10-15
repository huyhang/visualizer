// Where every goal and every dependency edge is drawn. Pure: plain data in,
// coordinates out, no DOM. Ported from the classic page's goallayout.js.
//
// The graph is ordered by *depth*, not by time: a goal sits one row below the
// deepest thing it rests on (the server computes that), so prerequisites are
// drawn above the goals that need them and every edge points downward.
//
// Three decisions are worth stating.
//
// **Goals with no edges at all are lifted into a band on top.** Most of a
// book's goals rest on nothing and carry nothing, and leaving them in the first
// layer makes it as wide as the book is long. They wrap into the width the
// connected part already takes, with a gap under the band so it does not read
// as the layer everything below depends on.
//
// **Rows are ordered by barycentre, not by name.** Each row after the first is
// sorted by the average position of what it rests on, which pulls a goal under
// its prerequisites; ties fall back to name so two reads draw the same picture.
//
// **Edges that skip a row bow outward**, so a long edge does not run behind the
// boxes in between and read as an edge to *those*.

export const NODE_W = 176;
// Two lines of name, the delivering scene, and that scene's date: the borrowed
// date is what makes the diagram readable as a chronology too.
export const NODE_H = 78;
export const GAP_X = 24;
export const GAP_Y = 64;
export const PAD = 16;
/** Extra room between the band of loose goals and the graph proper. */
export const BAND_GAP = 34;
export const ARROW_LEN = 10;
export const ARROW_WIDTH = 7;

export interface LayoutGoal {
  id: string;
  title?: string;
  depth?: number;
  depends_on?: string[];
}

export interface GoalNode {
  id: string;
  /** What the graph says, not which row it landed in: a loose goal is depth 0. */
  depth: number;
  column: number;
  island: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface GoalEdge {
  from: string;
  to: string;
  /** A cubic from the bottom of the prerequisite to just short of the arrow. */
  path: string;
  /** The arrowhead's three corners, tip first, as SVG polygon points. */
  arrow: string;
}

export interface GoalLayout {
  nodes: GoalNode[];
  edges: GoalEdge[];
  rows: number;
  band: number;
  width: number;
  height: number;
}

export interface LayoutOptions {
  /** The reader's text size relative to the default, so boxes grow with their words. */
  scale?: number;
}

const depthOf = (goal: LayoutGoal) => Math.max(0, Number(goal.depth) || 0);
const nameOf = (goal: LayoutGoal) => (goal.title || goal.id || "").toLowerCase();
const byName = (a: LayoutGoal, b: LayoutGoal) =>
  nameOf(a) < nameOf(b) ? -1 : nameOf(a) > nameOf(b) ? 1 : 0;

/**
 * Loose goals and joined-up ones. Loose means no line will be drawn to it: a
 * goal whose only prerequisite was deleted looks unattached, so it is treated
 * as unattached; the finding beside it says why.
 */
export function partition<T extends LayoutGoal>(
  goals: T[],
): { islands: T[]; connected: T[] } {
  const present = new Set(goals.map((g) => g.id));
  const needed = new Set(
    goals.flatMap((g) => (g.depends_on ?? []).filter((d) => present.has(d))),
  );
  const islands: T[] = [];
  const connected: T[] = [];
  for (const goal of goals) {
    const rests = (goal.depends_on ?? []).some((d) => present.has(d));
    (rests || needed.has(goal.id) ? connected : islands).push(goal);
  }
  return { islands: islands.sort(byName), connected };
}

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** The average position of what a goal rests on; Infinity sorts it to the row's end. */
function barycentre(goal: LayoutGoal, placed: Map<string, number>): number {
  const known = (goal.depends_on ?? []).flatMap((id) => {
    const at = placed.get(id);
    return at === undefined ? [] : [at];
  });
  if (!known.length) return Infinity;
  return known.reduce((sum, i) => sum + i, 0) / known.length;
}

/** Goals grouped into rows by depth, each row ordered to keep edges short. */
export function orderRows<T extends LayoutGoal>(goals: T[]): T[][] {
  const deepest = Math.max(-1, ...goals.map(depthOf));
  const rows: T[][] = [];
  const placed = new Map<string, number>();
  for (let depth = 0; depth <= deepest; depth += 1) {
    const row = goals.filter((g) => depthOf(g) === depth).sort(byName);
    row.sort((a, b) => {
      const pull = barycentre(a, placed) - barycentre(b, placed);
      return (Number.isNaN(pull) ? 0 : pull) || byName(a, b);
    });
    row.forEach((goal, index) => placed.set(goal.id, index));
    rows.push(row);
  }
  // Bad data still has to be drawn somewhere; the finding beside it explains.
  const stray = goals.filter((g) => !placed.has(g.id));
  if (stray.length) rows.push(stray.sort(byName));
  return rows;
}

/** A unit vector, straight down for a zero-length one. */
function unit(dx: number, dy: number): [number, number] {
  const len = Math.hypot(dx, dy);
  return len ? [dx / len, dy / len] : [0, 1];
}

/**
 * The curve and its arrowhead. Control points sit half a gap out from each
 * end, so the curve leaves and arrives vertically. The head is a polygon
 * rather than an SVG marker, so it takes the same class as its line and cannot
 * vanish to `url(#id)` resolving against a routed page's base.
 */
export function edgeGeometry(
  from: GoalNode,
  to: GoalNode,
  scale = 1,
): Pick<GoalEdge, "path" | "arrow"> {
  const x1 = from.x + from.width / 2;
  const y1 = from.y + from.height;
  const x2 = to.x + to.width / 2;
  const y2 = to.y;
  const span = Math.max(1, to.depth - from.depth);
  const lift = (y2 - y1) / 2;
  const bow = span > 1 ? (x2 > x1 ? 1 : -1) * (span - 1) * 28 * scale : 0;
  // The tangent at a cubic's end runs from the last control point to the endpoint.
  const [ux, uy] = unit(x2 - (x2 + bow), y2 - (y2 - lift));
  const head = ARROW_LEN * scale;
  const half = (ARROW_WIDTH * scale) / 2;
  // The line stops at the head's base, so it cannot show through as a spur.
  const bx = x2 - ux * head;
  const by = y2 - uy * head;
  return {
    path: `M ${x1} ${y1} C ${x1 + bow} ${y1 + lift}, ${x2 + bow} ${y2 - lift}, ${bx} ${by}`,
    arrow: [
      `${x2},${y2}`,
      `${bx - uy * half},${by + ux * half}`,
      `${bx + uy * half},${by - ux * half}`,
    ].join(" "),
  };
}

export function layoutGoals(
  goals: LayoutGoal[],
  { scale = 1 }: LayoutOptions = {},
): GoalLayout {
  const nodeWidth = NODE_W * scale;
  const nodeHeight = NODE_H * scale;
  const gapX = GAP_X * scale;
  const gapY = GAP_Y * scale;
  const pad = PAD * scale;

  const { islands, connected } = partition(goals);
  const graph = orderRows(connected);
  // The connected part sets the width and the loose goals wrap into it; with
  // nothing connected, the band goes roughly square rather than one long line.
  const graphColumns = Math.max(0, ...graph.map((row) => row.length));
  const columns = Math.max(graphColumns, Math.ceil(Math.sqrt(islands.length)), 1);
  const rows = [...chunk(islands, columns), ...graph];

  const widest = Math.max(1, ...rows.map((row) => row.length));
  const width = pad * 2 + widest * nodeWidth + (widest - 1) * gapX;
  const bandRows = Math.ceil(islands.length / columns);
  const bandGap = bandRows && graph.length ? BAND_GAP * scale : 0;

  const nodes: GoalNode[] = [];
  const at = new Map<string, GoalNode>();
  rows.forEach((row, index) => {
    const island = index < bandRows;
    // Centred against the widest row, so one root over four leaves reads as a fan.
    const rowWidth = row.length * nodeWidth + (row.length - 1) * gapX;
    const left = (width - rowWidth) / 2;
    row.forEach((goal, column) => {
      const node: GoalNode = {
        id: goal.id,
        depth: island ? 0 : index - bandRows,
        column,
        island,
        x: left + column * (nodeWidth + gapX),
        y: pad + index * (nodeHeight + gapY) + (island ? 0 : bandGap),
        width: nodeWidth,
        height: nodeHeight,
      };
      nodes.push(node);
      at.set(goal.id, node);
    });
  });

  const edges: GoalEdge[] = [];
  for (const goal of goals) {
    for (const dependency of goal.depends_on ?? []) {
      const from = at.get(dependency);
      const to = at.get(goal.id);
      if (!from || !to) continue; // a dangling id is reported, not drawn
      edges.push({ from: dependency, to: goal.id, ...edgeGeometry(from, to, scale) });
    }
  }

  const height =
    pad * 2 + rows.length * nodeHeight + Math.max(0, rows.length - 1) * gapY + bandGap;
  return { nodes, edges, rows: rows.length, band: bandRows, width, height };
}
