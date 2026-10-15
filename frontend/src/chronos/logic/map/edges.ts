// The shape of an edge. Ported from storygraph.js.
//
// A thread keeps its own column for the whole descent and turns *once*: right
// at the node it joins, or immediately after the node it leaves. A symmetric S
// would reach the target's column halfway down and then run on top of the line
// already descending it, so two threads would read as one.

/** How far before the node a thread starts to turn, before the distance across is added. */
export const TURN = 18;

export interface EdgeEnds {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export function edgeShape(e: EdgeEnds): string {
  if (e.x1 === e.x2) return `M ${e.x1} ${e.y1} L ${e.x2} ${e.y2}`;
  const span = Math.abs(e.y2 - e.y1);
  // Threads reaching further turn earlier and sweep wider, so several joining
  // one node nest instead of crossing.
  const turn = Math.min(span, TURN + Math.abs(e.x2 - e.x1) * 0.5);
  return e.x2 < e.x1
    ? `M ${e.x1} ${e.y1} V ${e.y2 - turn} Q ${e.x1} ${e.y2}, ${e.x2} ${e.y2}`
    : `M ${e.x1} ${e.y1} Q ${e.x2} ${e.y1}, ${e.x2} ${e.y1 + turn} V ${e.y2}`;
}

/** The class a dash pattern earns, so a thread's mark shows its stroke as well as its hue. */
export function strokeClass(dash: string): string {
  if (dash === "7 4") return "is-dashed";
  if (dash === "2 4") return "is-dotted";
  return "";
}
