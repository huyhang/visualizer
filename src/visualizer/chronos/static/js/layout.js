// Pure git-graph layout: a graph payload (nodes / edges / plotline lanes) in,
// numeric positions out. No DOM, no SVG, no fetches -- so it is the reusable
// heart shared by the connected-plots view now and the whole story map later
// (same function, just a bigger graph). storygraph.js turns this into SVG.
//
// Shape: threads run top-to-bottom in time (like the existing vertical
// timeline). Each plotline owns a column (lane); the focus thread is the
// leftmost spine. Every event is one node at a single row (its position in a
// time-ordered, edge-respecting sequence), so a shared event sits once and the
// other threads' edges curve into it -- that curve *is* the visible merge/split.

// -- geometry constants ------------------------------------------------------
const COL_W = 34;   // horizontal gap between lanes
const ROW_H = 58;   // vertical gap between events
const PAD_X = 22;   // left padding before the first lane
const PAD_TOP = 26; // top padding above the first row
const NODE_R = 7;   // node radius (storygraph reads this for hit targets)

export const geometry = { COL_W, ROW_H, PAD_X, PAD_TOP, NODE_R };

// A curated, theme-neutral categorical palette. Distinct hues, and none in the
// indigo/blue band reserved for the app accent (used to emphasise the focus).
const LANE_PALETTE = [
  "hsl(145deg 55% 45%)", // green
  "hsl(35deg 85% 50%)",  // amber
  "hsl(330deg 70% 55%)", // pink
  "hsl(178deg 55% 40%)", // teal
  "hsl(5deg 72% 56%)",   // red
  "hsl(90deg 48% 43%)",  // lime
  "hsl(288deg 45% 55%)", // violet
  "hsl(198deg 70% 46%)", // cyan
];

// A stable colour for the nth thread. Callers pass a thread's *global* index
// (its position in the whole book), so it keeps the same colour in every view and
// no matter which thread is focused -- the fix for colours shifting on re-centre.
// Wraps for books with more threads than palette entries.
export function paletteColor(n) {
  const len = LANE_PALETTE.length;
  return LANE_PALETTE[((n % len) + len) % len];
}

const _tick = (n) => (n && n.start_tick != null ? n.start_tick : Infinity);

// Order the lanes so the focus thread is column 0 (the spine); the rest keep the
// graph's own (name) order after it.
function orderLanes(plotlines, focusId) {
  const focus = plotlines.filter((p) => p.id === focusId);
  const rest = plotlines.filter((p) => p.id !== focusId);
  return [...focus, ...rest];
}

// Assign each node a row via a topological sort keyed by tick: edges always run
// downward (earlier row -> later row) regardless of scheduling, and scheduled
// scenes still fall in tick order. Robust to unscheduled scenes (tick = ∞, so
// they settle after their scheduled neighbours) without breaking edge direction.
function rowByNode(nodes, edges) {
  const tickOf = new Map(nodes.map((n) => [n.id, _tick(n)]));
  const indeg = new Map(nodes.map((n) => [n.id, 0]));
  const succ = new Map(nodes.map((n) => [n.id, []]));
  for (const e of edges) {
    if (!indeg.has(e.from) || !indeg.has(e.to)) continue;
    indeg.set(e.to, indeg.get(e.to) + 1);
    succ.get(e.from).push(e.to);
  }
  const cmp = (a, b) => (tickOf.get(a) - tickOf.get(b)) || (a < b ? -1 : 1);
  const row = new Map();
  const placed = new Set();
  let ready = [...indeg.keys()].filter((id) => indeg.get(id) === 0);
  let r = 0;
  while (ready.length) {
    ready.sort(cmp);
    const id = ready.shift();
    if (placed.has(id)) continue;
    row.set(id, r++);
    placed.add(id);
    for (const s of succ.get(id)) {
      indeg.set(s, indeg.get(s) - 1);
      if (indeg.get(s) === 0) ready.push(s);
    }
  }
  // Any leftover (only possible on a cycle, which the graph never has) settles by
  // tick so a bad payload still renders instead of vanishing.
  nodes.map((n) => n.id).filter((id) => !placed.has(id)).sort(cmp)
    .forEach((id) => row.set(id, r++));
  return row;
}

// Which lane a node is drawn in: the lowest-indexed lane that contains it. With
// the focus thread at index 0, every event the focus passes through lands on the
// spine, and other threads branch to/from it.
function laneByNode(nodeIds, lanes) {
  const lane = new Map();
  lanes.forEach((p, i) => {
    for (const eid of p.effective_events) {
      if (nodeIds.has(eid) && !lane.has(eid)) lane.set(eid, i);
    }
  });
  // A node no lane claims (shouldn't happen) falls to the spine.
  for (const id of nodeIds) if (!lane.has(id)) lane.set(id, 0);
  return lane;
}

function degrees(edges) {
  const indeg = {};
  const outdeg = {};
  for (const e of edges) {
    outdeg[e.from] = (outdeg[e.from] || 0) + 1;
    indeg[e.to] = (indeg[e.to] || 0) + 1;
  }
  return { indeg, outdeg };
}

// graph: { nodes, edges, plotlines, terminus, focus }
// opts.colorOf(plotlineId) -> colour string; pass a stable, book-wide mapping so
// a thread's colour never shifts between views. Falls back to this view's lane
// order when omitted (fine for standalone use / tests).
// Returns { width, height, lanes, nodes, edges, focus, hasUnscheduled }.
export function layoutGraph(graph, opts = {}) {
  const focusId = graph.focus;
  const lanes = orderLanes(graph.plotlines || [], focusId);
  const focusIndex = lanes.findIndex((p) => p.id === focusId);
  const colorOf = opts.colorOf || ((id) => paletteColor(lanes.findIndex((p) => p.id === id)));

  const laneMeta = lanes.map((p, i) => ({
    id: p.id,
    title: p.title || p.id,
    index: i,
    x: PAD_X + i * COL_W,
    color: colorOf(p.id),
    isFocus: i === focusIndex,
  }));

  const nodeIds = new Set((graph.nodes || []).map((n) => n.id));
  const row = rowByNode(graph.nodes || [], graph.edges || []);
  const lane = laneByNode(nodeIds, lanes);
  const { indeg, outdeg } = degrees(graph.edges || []);

  const xOf = (id) => PAD_X + (lane.get(id) || 0) * COL_W;
  const yOf = (id) => PAD_TOP + (row.get(id) || 0) * ROW_H;

  const nodes = (graph.nodes || []).map((n) => ({
    id: n.id,
    title: n.title || n.id,
    x: xOf(n.id),
    y: yOf(n.id),
    lane: lane.get(n.id) || 0,
    color: laneMeta[lane.get(n.id) || 0].color,
    isFocus: (lane.get(n.id) || 0) === focusIndex,
    scheduled: !!n.scheduled,
    startLabel: n.start_label,
    endLabel: n.end_label,
    startParts: n.start_parts,
    endParts: n.end_parts,
    startTick: n.start_tick,
    endTick: n.end_tick,
    // Roles are recomputed from *this* graph's edges, so a node that is only a
    // merge within the wider book but not among the shown threads reads honestly.
    isConvergence: (indeg[n.id] || 0) > 1,
    isDivergence: (outdeg[n.id] || 0) > 1,
    isTerminus: n.id === graph.terminus,
  }));

  // Colour each edge by its branch lane (the higher-indexed of its endpoints), so
  // a thread leaving/joining the spine is drawn in that thread's colour.
  const edges = (graph.edges || []).map((e) => {
    const branchLane = Math.max(lane.get(e.from) || 0, lane.get(e.to) || 0);
    return {
      from: e.from,
      to: e.to,
      x1: xOf(e.from), y1: yOf(e.from),
      x2: xOf(e.to), y2: yOf(e.to),
      color: laneMeta[branchLane].color,
      isFocus: branchLane === focusIndex,
      plotlines: e.plotlines,
    };
  });

  const rows = Math.max(0, ...[...row.values()].map((r) => r + 1));
  const width = PAD_X + Math.max(1, lanes.length) * COL_W;
  const height = PAD_TOP + rows * ROW_H;

  return {
    width,
    height,
    lanes: laneMeta,
    nodes,
    edges,
    focus: focusId,
    hasUnscheduled: nodes.some((n) => !n.scheduled),
  };
}
