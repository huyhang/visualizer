// Pure git-graph layout: a graph payload (nodes / edges / plotline lanes) in,
// numeric positions out. No DOM, no SVG, no fetches -- so it is the reusable
// heart shared by the story map and the connected-plots slice it grew out of.
// storygraph.js turns what this returns into SVG.
//
// Shape: threads run top-to-bottom in time (like the single-plotline timeline).
// Each plotline owns a column (lane); every event is one node at a single row
// (its position in a time-ordered, edge-respecting sequence), so a shared event
// sits once and the other threads' edges curve into it -- that curve *is* the
// visible merge/split.
//
// Two things are injected rather than fixed, because the map varies them per
// view and the tests drive them directly:
//
//   colorOf(plotlineId) -> a thread's colour. Callers pass a *book-wide* mapping
//     so a thread keeps one colour in every view and never shifts when the
//     selection changes.
//   heightOf(node) -> a row's height. Constant for collapsed rows; an expanded
//     scene card reports its measured height, and every row below it moves down.

import { groupByPeriod } from "./timeaxis.js";

// -- geometry constants ------------------------------------------------------
const COL_W = 34;       // horizontal gap between lanes
const ROW_H = 58;       // vertical gap between events
const ROW_COMPACT = 32; // ...in compact density
const PAD_X = 22;       // left padding before the first lane
const PAD_TOP = 26;     // top padding above the first row
const NODE_R = 7;       // node radius (storygraph reads this for hit targets)
const HEADER_H = 30;    // vertical room a calendar period band takes
// The narrowest the event titles may ever be squeezed. Past this the lane gutter
// scrolls instead of eating the text: `.sg-row` is absolutely positioned at a
// computed y but wraps its content, so a too-narrow column makes rows *overlap*
// rather than merely look cramped.
const TEXT_MIN = 420;

export const geometry = {
  COL_W, ROW_H, ROW_COMPACT, PAD_X, PAD_TOP, NODE_R, HEADER_H, TEXT_MIN,
};

// A curated, theme-neutral categorical palette. Distinct hues, none in the
// indigo/blue band reserved for the app accent.
const LANE_PALETTE = [
  "hsl(145deg 55% 45%)", // green
  "hsl(35deg 85% 50%)",  // amber
  "hsl(330deg 70% 55%)", // pink
  "hsl(178deg 55% 40%)", // teal
  "hsl(5deg 72% 56%)",   // red
  "hsl(90deg 48% 43%)",  // lime
  "hsl(288deg 45% 55%)", // violet
  "hsl(198deg 70% 46%)", // cyan
  "hsl(20deg 45% 42%)",  // russet
  "hsl(160deg 40% 62%)", // mint
  "hsl(310deg 55% 40%)", // mulberry
  "hsl(55deg 60% 42%)",  // olive
];

// Hue runs out long before threads do, so identity rides on two channels: after
// a full turn of the palette the same hue returns in a different stroke, and the
// legend shows the pairing. Twelve hues x three strokes tells apart far more
// threads than a map stays readable at -- which is the point. The writer meets
// the *visual* ceiling rather than a silent colour collision.
const LANE_DASHES = ["", "7 4", "2 4"]; // solid, dashed, dotted

// A stable colour for the nth thread. Callers pass a thread's *global* index (its
// position in the whole book), so it keeps the same colour in every view no
// matter what else is selected.
export function paletteColor(n) {
  const len = LANE_PALETTE.length;
  return LANE_PALETTE[((n % len) + len) % len];
}

// The stroke that goes with that colour -- see LANE_DASHES. "" means solid.
export function paletteDash(n) {
  const turn = Math.floor(Math.abs(n) / LANE_PALETTE.length);
  return LANE_DASHES[turn % LANE_DASHES.length];
}

// -- time order --------------------------------------------------------------

function adjacency(nodes, edges) {
  const preds = new Map(nodes.map((n) => [n.id, []]));
  const succs = new Map(nodes.map((n) => [n.id, []]));
  for (const e of edges) {
    if (!preds.has(e.to) || !succs.has(e.from)) continue;
    preds.get(e.to).push(e.from);
    succs.get(e.from).push(e.to);
  }
  return { preds, succs };
}

// Kahn's algorithm, taking the cheapest ready node each time. `keyOf` decides
// what "cheapest" means; ids break every tie, so the result is deterministic.
function topoOrder(nodes, edges, keyOf) {
  const indeg = new Map(nodes.map((n) => [n.id, 0]));
  const { succs } = adjacency(nodes, edges);
  for (const e of edges) {
    if (!indeg.has(e.from) || !indeg.has(e.to)) continue;
    indeg.set(e.to, indeg.get(e.to) + 1);
  }
  const cmp = (a, b) => (keyOf(a) - keyOf(b)) || (a < b ? -1 : 1);
  const ready = [...indeg.keys()].filter((id) => indeg.get(id) === 0);
  const out = [];
  const placed = new Set();
  while (ready.length) {
    ready.sort(cmp);
    const id = ready.shift();
    if (placed.has(id)) continue;
    out.push(id);
    placed.add(id);
    for (const s of succs.get(id)) {
      indeg.set(s, indeg.get(s) - 1);
      if (indeg.get(s) === 0) ready.push(s);
    }
  }
  // Anything left is in a cycle, which the graph never has -- settle it by key
  // so a bad payload still renders instead of vanishing.
  out.push(...nodes.map((n) => n.id).filter((id) => !placed.has(id)).sort(cmp));
  return out;
}

// The tick each row sorts by.
//
// A scheduled scene has one. An **unscheduled** scene has to be given one, and
// the choice matters more than it looks: treating it as "infinitely late" (the
// obvious reading) does not merely park that scene at the bottom, it drags every
// scene downstream of it down too, because a thread's scenes are chained. One
// undated scene early in a thread was enough to push the rest of that thread
// below scenes a year later -- and then the calendar rail, walking rows in
// order, announced Year 2 and doubled back to Year 1.
//
// So an undated scene sits where its neighbours imply, which is what the rest of
// Chronos already means by an unscheduled scene (design §4, and the window the
// single-plotline timeline shows): midway between the latest thing that must
// precede it and the earliest that must follow. Only a scene with no dated
// neighbour at all is genuinely unplaceable, and those settle at the end.
function effectiveTicks(nodes, edges) {
  const { preds, succs } = adjacency(nodes, edges);
  const own = new Map(nodes.map((n) => [n.id, n.start_tick != null ? n.start_tick : null]));
  const order = topoOrder(nodes, edges, () => 0);

  const after = new Map();  // earliest this can be, from what precedes it
  for (const id of order) {
    const known = preds.get(id).map((p) => after.get(p)).filter((v) => v != null);
    after.set(id, own.get(id) != null ? own.get(id) : (known.length ? Math.max(...known) : null));
  }
  const before = new Map(); // latest this can be, from what follows it
  for (const id of [...order].reverse()) {
    const known = succs.get(id).map((s) => before.get(s)).filter((v) => v != null);
    before.set(id, own.get(id) != null ? own.get(id) : (known.length ? Math.min(...known) : null));
  }

  const eff = new Map();
  for (const n of nodes) {
    if (own.get(n.id) != null) { eff.set(n.id, own.get(n.id)); continue; }
    const lo = after.get(n.id);
    const hi = before.get(n.id);
    if (lo != null && hi != null) eff.set(n.id, (lo + hi) / 2);
    else if (lo != null) eff.set(n.id, lo);
    else if (hi != null) eff.set(n.id, hi);
    else eff.set(n.id, Infinity);
  }
  return eff;
}

// -- lane ordering -----------------------------------------------------------

// How many events each pair of threads shares. The terminus is excluded: every
// plotline ends there by rule, so counting it would pull every lane toward every
// other one equally and say nothing about who actually meets whom.
function sharedCounts(lanes, terminus) {
  const sets = lanes.map(
    (p) => new Set((p.effective_events || []).filter((e) => e !== terminus)),
  );
  const weight = lanes.map(() => new Map());
  for (let i = 0; i < lanes.length; i++) {
    for (let j = i + 1; j < lanes.length; j++) {
      let n = 0;
      for (const e of sets[i]) if (sets[j].has(e)) n++;
      if (n) { weight[i].set(j, n); weight[j].set(i, n); }
    }
  }
  return weight;
}

// What an arrangement costs: every pair of threads that meet, weighted by how
// often, times how many columns apart they sit. Minimising it is exactly what
// makes the curves short, because a shared event is drawn once in the
// lowest-indexed lane holding it and every other thread through it has to cross
// whatever lies between.
function arrangementCost(order, weight) {
  const pos = new Map(order.map((laneIdx, column) => [laneIdx, column]));
  let cost = 0;
  for (const laneIdx of order) {
    for (const [other, w] of weight[laneIdx]) {
      if (laneIdx < other) cost += w * Math.abs(pos.get(laneIdx) - pos.get(other));
    }
  }
  return cost;
}

// One barycentre sweep: move each thread to the weighted average position of the
// threads it meets, then re-sort. A good global arrangement in one shot -- but
// on small graphs it can oscillate between two equally mediocre orders, which is
// why it is a *candidate* here rather than the answer.
function barycentreSweep(order, weight) {
  const pos = new Map(order.map((laneIdx, column) => [laneIdx, column]));
  const bary = new Map(order.map((laneIdx) => {
    let sum = 0;
    let total = 0;
    for (const [other, w] of weight[laneIdx]) {
      sum += w * pos.get(other);
      total += w;
    }
    return [laneIdx, total ? sum / total : pos.get(laneIdx)];
  }));
  return [...order].sort(
    (a, b) => (bary.get(a) - bary.get(b)) || (a - b), // book order breaks ties
  );
}

// Adjacent-swap descent: keep exchanging neighbouring columns while it lowers
// the cost. Monotonic, so it can only improve on what it was given, and it ends
// -- which together are what let this promise never to be worse than the book's
// own order.
function polish(order, weight, rounds = 8) {
  const out = [...order];
  for (let round = 0; round < rounds; round++) {
    let moved = false;
    for (let i = 0; i + 1 < out.length; i++) {
      const before = arrangementCost(out, weight);
      [out[i], out[i + 1]] = [out[i + 1], out[i]];
      if (arrangementCost(out, weight) < before) moved = true;
      else [out[i], out[i + 1]] = [out[i + 1], out[i]]; // put it back
    }
    if (!moved) break;
  }
  return out;
}

// Order the lanes so threads that meet sit near each other. The book's own
// (name) order is arbitrary with respect to who meets whom, so a book tangles as
// soon as it has a few threads.
//
// Two candidates -- the book's order, and one barycentre sweep away from it --
// each polished by adjacent-swap descent, and the cheaper one wins with ties
// going to the book. So the result is deterministic, never worse than the order
// it started from, and a thread's *column* moves only when the selection
// changes. Its colour, keyed to the book-wide index, never moves at all.
export function orderLanes(plotlines, { terminus = null } = {}) {
  const lanes = [...(plotlines || [])];
  if (lanes.length < 3) return lanes; // nothing to untangle
  const weight = sharedCounts(lanes, terminus);

  const book = lanes.map((_, i) => i); // order[column] = index into `lanes`
  const candidates = [polish(book, weight), polish(barycentreSweep(book, weight), weight)];
  const best = candidates.reduce(
    (a, b) => (arrangementCost(b, weight) < arrangementCost(a, weight) ? b : a),
  );
  return best.map((i) => lanes[i]);
}

// Assign each node a row: a topological sort keyed by effective tick, so edges
// always run downward (earlier row -> later row) and scenes still fall in time
// order. The two can only disagree when a plotline lists its scenes out of tick
// order -- which is an ordering violation the book already reports -- and there
// the edge wins, because a thread that visibly doubles back is the honest
// drawing of a thread that does.
function rowByNode(nodes, edges) {
  const eff = effectiveTicks(nodes, edges);
  const order = topoOrder(nodes, edges, (id) => eff.get(id));
  return new Map(order.map((id, index) => [id, index]));
}

// Which lane a node is drawn in: the lowest-indexed lane that contains it, so
// every event on the leftmost thread through it lands on that thread's column
// and the others branch to and from it.
function laneByNode(nodeIds, lanes) {
  const lane = new Map();
  lanes.forEach((p, i) => {
    for (const eid of p.effective_events) {
      if (nodeIds.has(eid) && !lane.has(eid)) lane.set(eid, i);
    }
  });
  // A node no lane claims (shouldn't happen) falls to the first column.
  for (const id of nodeIds) if (!lane.has(id)) lane.set(id, 0);
  return lane;
}

// Which column each occupied lane gets, once the empty ones are closed up.
// Order is preserved -- the leftmost thread stays leftmost -- so only the blank
// space between disappears. Lanes that hold nothing get no seat at all: a thread
// whose every scene also sits on an earlier one (a trunk the others continue
// into) is never drawn in a column of its own, and reserving one for it was
// blank gutter plus a resize with nothing behind it.
function seats(lane) {
  const used = [...new Set(lane.values())].sort((a, b) => a - b);
  return new Map(used.map((laneIdx, column) => [laneIdx, column]));
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

// Stack rows of varying height, centring each one in the space it takes. Shared
// by the plain layout and the period-grouped one, so a row's height is honoured
// identically whether or not calendar bands are in play.
function stackRows(ordered, heightOf, startY) {
  const centre = new Map();
  let y = startY;
  for (const n of ordered) {
    const h = heightOf(n);
    centre.set(n.id, y + h / 2);
    y += h;
  }
  return { centre, bottom: y };
}

// graph: { nodes, edges, plotlines, terminus, focus }
// opts.colorOf(id) / opts.dashOf(id) / opts.heightOf(node) -- see the top note.
// Returns { width, minWidth, height, lanes, nodes, edges, focus, hasUnscheduled }.
export function layoutGraph(graph, opts = {}) {
  const focusId = graph.focus;
  const lanes = orderLanes(graph.plotlines || [], { terminus: graph.terminus });
  const focusIndex = lanes.findIndex((p) => p.id === focusId);
  const colorOf = opts.colorOf || ((id) => paletteColor(lanes.findIndex((p) => p.id === id)));
  const dashOf = opts.dashOf || ((id) => paletteDash(lanes.findIndex((p) => p.id === id)));
  const heightOf = opts.heightOf || (() => ROW_H);

  const laneMeta = lanes.map((p, i) => ({
    id: p.id,
    title: p.title || p.id,
    index: i,
    color: colorOf(p.id),
    dash: dashOf(p.id),
    isFocus: i === focusIndex,
  }));

  const nodeIds = new Set((graph.nodes || []).map((n) => n.id));
  const row = rowByNode(graph.nodes || [], graph.edges || []);
  // Two different numbers, and conflating them costs a thread its colour: `lane`
  // is *which thread* a node is drawn on (identity -- colour, dash, focus), and
  // `column` is *where* that lands once the empty ones are closed up (geometry).
  const lane = laneByNode(nodeIds, lanes);
  const seat = seats(lane);
  const { indeg, outdeg } = degrees(graph.edges || []);

  const laneOf = (id) => lane.get(id) || 0;
  const columnOf = (id) => seat.get(laneOf(id)) || 0;
  const xOf = (id) => PAD_X + columnOf(id) * COL_W;
  laneMeta.forEach((l) => {
    l.column = seat.has(l.index) ? seat.get(l.index) : null;
    l.x = l.column == null ? null : PAD_X + l.column * COL_W;
  });

  const nodes = (graph.nodes || []).map((n) => ({
    id: n.id,
    title: n.title || n.id,
    row: row.get(n.id) || 0,
    x: xOf(n.id),
    lane: laneOf(n.id),
    column: columnOf(n.id),
    color: laneMeta[laneOf(n.id)].color,
    dash: laneMeta[laneOf(n.id)].dash,
    isFocus: laneOf(n.id) === focusIndex,
    scheduled: !!n.scheduled,
    startLabel: n.start_label,
    endLabel: n.end_label,
    startParts: n.start_parts,
    endParts: n.end_parts,
    startTick: n.start_tick,
    endTick: n.end_tick,
    // A collapsed run of scenes one thread walks alone (see collapse.js). It
    // rides as an ordinary row; only the renderer cares that it unfolds.
    isBand: !!n.is_band,
    events: n.events || null,
    laneTitle: n.lane_title || null,
    // Roles are recomputed from *this* graph's edges, so a node that is only a
    // merge within the wider book but not among the shown threads reads honestly.
    isConvergence: (indeg[n.id] || 0) > 1,
    isDivergence: (outdeg[n.id] || 0) > 1,
    isTerminus: n.id === graph.terminus,
  }));

  const ordered = [...nodes].sort((a, b) => a.row - b.row);
  const { centre, bottom } = stackRows(ordered, heightOf, PAD_TOP);
  nodes.forEach((n) => { n.y = centre.get(n.id); });

  // Colour each edge by its branch lane (the higher-indexed of its endpoints), so
  // a thread leaving or joining another is drawn in that thread's own colour.
  const edges = (graph.edges || []).map((e) => {
    const branchLane = Math.max(laneOf(e.from), laneOf(e.to));
    return {
      from: e.from,
      to: e.to,
      x1: xOf(e.from), y1: centre.get(e.from),
      x2: xOf(e.to), y2: centre.get(e.to),
      color: laneMeta[branchLane].color,
      dash: laneMeta[branchLane].dash,
      isFocus: branchLane === focusIndex,
      plotlines: e.plotlines,
    };
  });

  // Sized by the columns that hold something, not by how many threads are
  // ticked. A thread whose every event also sits on an earlier one -- a trunk the
  // others continue into -- never owns a column, and reserving one for it was
  // both blank space and a resize with nothing behind it: toggling that thread
  // moved the whole title column while changing not one mark in the drawing.
  const width = PAD_X + Math.max(1, seat.size) * COL_W;
  return {
    width,
    // What the drawing needs before the titles start being squeezed. The view
    // scrolls the pane horizontally rather than let the text column shrink past
    // it -- see TEXT_MIN.
    minWidth: width + 12 + TEXT_MIN,
    height: bottom,
    lanes: laneMeta,
    nodes,
    edges,
    focus: focusId,
    hasUnscheduled: nodes.some((n) => !n.scheduled),
  };
}

// Promote coarse calendar components (Year, Month, …) into period header bands
// and keep only the fine part on each event row -- exactly how the single-plotline
// timeline reads -- by running the shared `groupByPeriod` grouper over the nodes
// in row order. Headers take vertical room, so node/edge y are recomputed from
// the grouped sequence (and edges just span the larger gaps).
//
// The unit of vertical space is a **slot**, not a node: scenes that happen at the
// same moment share one, so they share one y (see `slots`). Everything that draws
// -- dots, edges, rows -- reads its y from here, so the diagram and the text
// cannot disagree about what is simultaneous.
//
// Pure: a layout in, a drawing model out.
export function applyPeriodGrouping(layout, opts = {}) {
  const heightOf = opts.heightOf || (() => ROW_H);
  const collapsed = opts.collapsedMoments instanceof Set
    ? opts.collapsedMoments : new Set(opts.collapsedMoments || []);
  const ordered = [...layout.nodes].sort((a, b) => a.row - b.row);
  // Adapter objects in the shape groupByPeriod expects (snake_case + parts).
  const adapters = ordered.map((n) => ({
    scheduled: n.scheduled,
    start_label: n.startLabel,
    end_label: n.endLabel,
    start_parts: n.startParts,
    end_parts: n.endParts,
    _node: n,
  }));

  const headers = [];
  const when = new Map(); // node id -> compact period label
  const sequence = [];    // headers and event rows, in the order they are drawn
  for (const item of groupByPeriod(adapters)) {
    if (item.type === "header") sequence.push({ header: item });
    else {
      when.set(item.event._node.id, item.label);
      sequence.push({ node: item.event._node });
    }
  }

  // Batch the rows into slots, then give each slot its space.
  const built = [];
  let y = PAD_TOP;
  for (const slot of slots(sequence, collapsed)) {
    if (slot.header) {
      headers.push({ level: slot.header.level, label: slot.header.label, y });
      y += HEADER_H;
      continue;
    }
    const h = heightOf(slot.isGroup ? slot : slot.nodes[0]);
    built.push({ ...slot, top: y, y: y + h / 2, bottom: y + h, when: when.get(slot.nodes[0].id) });
    y += h;
  }

  const cy = new Map();
  built.forEach((slot) => slot.nodes.forEach((n) => cy.set(n.id, slot.y)));

  const nodes = ordered.map((n) => ({ ...n, y: cy.get(n.id), when: when.get(n.id) }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const rows = built.map((slot) => ({
    ...slot,
    nodes: slot.nodes.map((n) => byId.get(n.id)),
  }));
  const edges = layout.edges.map((e) => ({ ...e, y1: cy.get(e.from), y2: cy.get(e.to) }));
  return {
    headers,
    rows,
    nodes,
    edges,
    lanes: layout.lanes,
    width: layout.width,
    minWidth: layout.minWidth,
    height: y + 8,
  };
}

// A group's identity has to survive a redraw, because the set of unmerged ones is
// keyed by it. Its tick and its first scene name it: both are stable for as long
// as the coincidence itself is.
export const groupId = (nodes) => `~at:${nodes[0].startTick}:${nodes[0].id}`;

// Rows that start on the same tick are not a sequence -- they are things
// happening at once, on different threads. (A plotline's own scenes can never
// share a tick: the ordering rule requires each to end before the next begins.
// So this only ever groups *across* threads, which is what a map is for.)
//
// Given a row each they stack, and a vertical timeline reads a stack as "this,
// then that" -- an order that is not in the story, and that here is only an
// alphabetical tie-break from the topological sort. So they share one slot: one
// y, one time, every scene's dot at the same height on its own thread.
//
// A moment is a node in a tree, and its twisty means what it means everywhere
// else: open, its scenes are listed; closed, they are hidden behind a count. It
// is open by default, because a scene you cannot read is not much of a map.
function slots(sequence, collapsed) {
  const out = [];
  let run = [];

  const flush = () => {
    if (!run.length) return;
    if (run.length > 1) {
      const id = groupId(run);
      out.push({
        id, nodes: [...run], isGroup: true, count: run.length,
        collapsed: collapsed.has(id),
      });
    } else {
      out.push({ id: run[0].id, nodes: [run[0]] });
    }
    run = [];
  };

  for (const item of sequence) {
    if (item.header) { flush(); out.push({ header: item.header }); continue; }
    const n = item.node;
    // An undated scene has no tick to coincide with, so it never groups.
    if (!n.scheduled || n.startTick == null) { flush(); out.push({ id: n.id, nodes: [n] }); continue; }
    if (run.length && run[run.length - 1].startTick === n.startTick) run.push(n);
    else { flush(); run = [n]; }
  }
  flush();
  return out;
}
