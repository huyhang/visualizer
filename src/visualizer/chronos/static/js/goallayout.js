// Where every goal and every dependency edge is drawn. Pure: plain data in,
// coordinates out, no DOM — so `tests/chronos/test_goal_layout_js.py` drives it
// directly under node, the same bargain `layout.js` strikes for the story map.
//
// The dependency graph is ordered by *depth*, not by time: a goal sits one row
// below the deepest thing it rests on (the server computes that — see
// `goal_rules.depths`). So the drawing is layered top to bottom, prerequisites
// above the goals that need them, and every edge points downward.
//
// Three decisions are worth stating.
//
// **Goals with no edges at all are lifted out into a band on top.** In practice
// most of a book's goals rest on nothing and carry nothing — they are simply
// things the story means to do — and leaving them in the graph's first layer
// makes that layer as wide as the book is long, for no information at all. They
// wrap into as many short lines as they need, bounded by the width the connected
// part already takes, so the whole diagram is as wide as the *graph* rather than
// as wide as the list. A gap under the band keeps it from reading as the layer
// everything below depends on.
//
// **Rows are ordered by barycentre, not by name.** Name order is arbitrary with
// respect to who depends on whom, and it crosses edges for no reason. Each row
// after the first is sorted by the average position of the goals it rests on,
// which pulls a goal underneath its prerequisites; ties fall back to name so the
// result is stable and two reads of one book draw the same picture.
//
// **Edges that skip a row bow outward.** A goal may rest on something three rows
// up, and a straight line between them would run underneath the boxes in
// between — which reads as an edge to *those*. Bowing sideways in proportion to
// the rows it crosses keeps a long edge visibly separate from the short ones.

export const NODE_W = 176;
export const NODE_H = 62;
export const GAP_X = 24;
export const GAP_Y = 64;
export const PAD = 16;
// Extra room between the band of loose goals and the graph proper.
export const BAND_GAP = 34;
// The arrowhead, drawn as a triangle rather than an SVG marker (see below).
export const ARROW_LEN = 10;
export const ARROW_WIDTH = 7;

// `scale` is the reader's text size relative to the default (the app's font
// toggle sets the root font size, and the labels are in rem). The boxes are
// positioned in px, so without it a larger text size would grow the words
// inside boxes that stayed the same size — and the diagram would slowly clip
// itself. Scaling the whole layout keeps a box the same size *relative to the
// text in it* at every setting.
export function layoutGoals(goals, opts = {}) {
  const { scale = 1 } = opts;
  const {
    nodeWidth = NODE_W * scale, nodeHeight = NODE_H * scale,
    gapX = GAP_X * scale, gapY = GAP_Y * scale, pad = PAD * scale,
  } = opts;

  const { islands, connected } = partition(goals);
  const graph = orderRows(connected);
  // The connected part sets the diagram's width, and the loose goals wrap into
  // it. A book with nothing connected has no width to borrow, so its band goes
  // roughly square rather than into one very long line.
  const graphColumns = Math.max(0, ...graph.map((row) => row.length));
  const columns = Math.max(graphColumns, Math.ceil(Math.sqrt(islands.length)), 1);
  const rows = [...chunk(islands, columns), ...graph];

  const widest = Math.max(1, ...rows.map((row) => row.length));
  const width = pad * 2 + widest * nodeWidth + (widest - 1) * gapX;

  const bandRows = Math.ceil(islands.length / columns);
  // A wider gap where the band meets the graph, so the two read as two things.
  // Without it the last row of loose goals looks like the graph's top layer —
  // as though everything below depended on it.
  const bandGap = bandRows && graph.length ? BAND_GAP * scale : 0;

  const nodes = [];
  const at = new Map();
  rows.forEach((row, index) => {
    const island = index < bandRows;
    // Centred against the widest row, so a book with one root and four leaves
    // reads as a fan rather than as everything shoved left.
    const rowWidth = row.length * nodeWidth + (row.length - 1) * gapX;
    const left = (width - rowWidth) / 2;
    row.forEach((goal, column) => {
      const node = {
        id: goal.id,
        // What the *graph* says, not which row this landed in: a loose goal
        // rests on nothing, whichever line of the band it wrapped onto.
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

  const edges = [];
  for (const goal of goals) {
    for (const dependency of goal.depends_on || []) {
      const from = at.get(dependency);
      const to = at.get(goal.id);
      if (!from || !to) continue; // a dangling id is reported, not drawn
      edges.push({ from: dependency, to: goal.id, ...edgeGeometry(from, to, scale) });
    }
  }

  const height = pad * 2 + rows.length * nodeHeight
    + Math.max(0, rows.length - 1) * gapY + bandGap;
  return { nodes, edges, rows: rows.length, band: bandRows, width, height };
}

// Loose goals and joined-up ones. "Loose" means *no line will be drawn to it* —
// nothing in this book depends on it, and it depends on nothing this book still
// has. A goal whose only prerequisite has been deleted looks unattached on the
// page, so it is treated as unattached here; the finding beside it says why.
function partition(goals) {
  const present = new Set(goals.map((g) => g.id));
  const needed = new Set(
    goals.flatMap((g) => (g.depends_on || []).filter((d) => present.has(d)))
  );
  const islands = [];
  const connected = [];
  for (const goal of goals) {
    const rests = (goal.depends_on || []).some((d) => present.has(d));
    (rests || needed.has(goal.id) ? connected : islands).push(goal);
  }
  return { islands: islands.sort(byName), connected };
}

function chunk(items, size) {
  const out = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

// Goals grouped into rows by depth, each row ordered to keep edges short.
function orderRows(goals) {
  const deepest = Math.max(-1, ...goals.map((g) => depthOf(g)));
  const rows = [];
  const placed = new Map(); // id -> its index within its row

  for (let depth = 0; depth <= deepest; depth += 1) {
    const row = goals.filter((g) => depthOf(g) === depth).sort(byName);
    row.sort((a, b) => {
      const pull = barycentre(a, placed) - barycentre(b, placed);
      return pull || byName(a, b);
    });
    row.forEach((goal, index) => placed.set(goal.id, index));
    rows.push(row);
  }
  // A goal whose depth is out of range (bad data, or a graph that loops) still
  // has to be drawn somewhere; the last row is somewhere, and the loop itself
  // is reported next to it.
  const stray = goals.filter((g) => !placed.has(g.id));
  if (stray.length) rows.push(stray.sort(byName));
  return rows;
}

const depthOf = (goal) => Math.max(0, Number(goal.depth) || 0);
const nameOf = (goal) => (goal.name || goal.title || goal.id || "").toLowerCase();
const byName = (a, b) => (nameOf(a) < nameOf(b) ? -1 : nameOf(a) > nameOf(b) ? 1 : 0);

// The average position of what this goal rests on. Infinity when it rests on
// nothing placed yet, which sorts those goals to the end of their row rather
// than pretending they belong at the left edge.
function barycentre(goal, placed) {
  const known = (goal.depends_on || []).map((id) => placed.get(id)).filter((i) => i != null);
  if (!known.length) return Infinity;
  return known.reduce((sum, i) => sum + i, 0) / known.length;
}

// A cubic from the bottom of the prerequisite to the top of the goal that needs
// it, plus the triangle that lands on the target. Control points sit half a gap
// out from each end, so the curve leaves and arrives vertically — an edge that
// met a box at an angle would look like it was pointing at the box beside it.
function edgeGeometry(from, to, scale) {
  const x1 = from.x + from.width / 2;
  const y1 = from.y + from.height;
  const x2 = to.x + to.width / 2;
  const y2 = to.y;
  const span = Math.max(1, to.depth - from.depth);
  const lift = (y2 - y1) / 2;
  // Rows skipped are rows this edge passes *behind*; bowing it out by a fixed
  // step per row keeps it clear of them. Direction follows the way the edge is
  // already leaning, and a vertical edge bows left rather than picking at random.
  const bow = span > 1 ? (x2 > x1 ? 1 : -1) * (span - 1) * 28 * scale : 0;

  // The direction the curve is travelling as it arrives: for a cubic, the
  // tangent at the end is simply the last control point to the endpoint.
  const [ux, uy] = unit(x2 - (x2 + bow), y2 - (y2 - lift));
  const head = ARROW_LEN * scale;
  const half = (ARROW_WIDTH * scale) / 2;
  // The line stops at the head's base rather than at the box, so it cannot show
  // through the triangle as a spur past the tip.
  const bx = x2 - ux * head;
  const by = y2 - uy * head;
  return {
    path: `M ${x1} ${y1} C ${x1 + bow} ${y1 + lift}, ${x2 + bow} ${y2 - lift}, ${bx} ${by}`,
    // Tip on the box, two base corners square to the direction of travel. A
    // polygon rather than an SVG `marker`: a marker is drawn out of `defs` and
    // inherits nothing from the path referencing it, so highlighting one edge
    // meant defining a second marker and hoping the two stayed in step. This
    // triangle is a sibling of its line and simply takes the same class. It
    // also sidesteps `url(#id)` resolving against the document base, which is
    // the usual way arrowheads vanish on a page that is served under a route.
    arrow: [
      `${x2},${y2}`,
      `${bx - uy * half},${by + ux * half}`,
      `${bx + uy * half},${by - ux * half}`,
    ].join(" "),
  };
}

// A unit vector, defaulting to straight down for a zero-length one -- which is
// what an edge between two boxes on the same row would give, and only bad data
// puts two goals of one dependency on the same row.
function unit(dx, dy) {
  const len = Math.hypot(dx, dy);
  return len ? [dx / len, dy / len] : [0, 1];
}
