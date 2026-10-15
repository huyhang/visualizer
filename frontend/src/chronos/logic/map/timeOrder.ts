// Which row each scene gets: a topological sort keyed by time, so edges always
// run downward and scenes still fall in time order. Ported from layout.js.
//
// The two disagree only when a thread lists its scenes out of order -- a
// violation the book already reports -- and there the edge wins, because a
// thread that visibly doubles back is the honest drawing of one that does.

interface Linked {
  id: string;
}
interface Edge {
  from: string;
  to: string;
}

function adjacency(nodes: Linked[], edges: Edge[]) {
  const preds = new Map(nodes.map((n) => [n.id, [] as string[]]));
  const succs = new Map(nodes.map((n) => [n.id, [] as string[]]));
  for (const e of edges) {
    if (!preds.has(e.to) || !succs.has(e.from)) continue;
    preds.get(e.to)?.push(e.from);
    succs.get(e.from)?.push(e.to);
  }
  return { preds, succs };
}

/** Kahn's algorithm, taking the cheapest ready node each time; ids break ties, so it is deterministic. */
export function topoOrder(
  nodes: Linked[],
  edges: Edge[],
  keyOf: (id: string) => number,
): string[] {
  const indeg = new Map(nodes.map((n) => [n.id, 0]));
  const { succs } = adjacency(nodes, edges);
  for (const e of edges) {
    if (indeg.has(e.from) && indeg.has(e.to)) indeg.set(e.to, (indeg.get(e.to) ?? 0) + 1);
  }
  const cmp = (a: string, b: string) => keyOf(a) - keyOf(b) || (a < b ? -1 : 1);
  const ready = [...indeg.keys()].filter((id) => indeg.get(id) === 0);
  const out: string[] = [];
  const placed = new Set<string>();
  while (ready.length) {
    ready.sort(cmp);
    const id = ready.shift() as string;
    if (placed.has(id)) continue;
    out.push(id);
    placed.add(id);
    for (const s of succs.get(id) ?? []) {
      indeg.set(s, (indeg.get(s) ?? 0) - 1);
      if (indeg.get(s) === 0) ready.push(s);
    }
  }
  // A cycle (which the graph never has) settles by key, so a bad payload still draws.
  out.push(
    ...nodes
      .map((n) => n.id)
      .filter((id) => !placed.has(id))
      .sort(cmp),
  );
  return out;
}

const maxOf = (values: (number | null | undefined)[]) => {
  const known = values.filter((v): v is number => v !== null && v !== undefined);
  return known.length ? Math.max(...known) : null;
};
const minOf = (values: (number | null | undefined)[]) => {
  const known = values.filter((v): v is number => v !== null && v !== undefined);
  return known.length ? Math.min(...known) : null;
};

/**
 * The tick each row sorts by. An undated scene sits where its neighbours put
 * it -- midway between the latest thing before it and the earliest after --
 * rather than "infinitely late", which would drag every scene after it on its
 * thread below scenes a year later. Only a scene with no dated neighbour at
 * all settles at the end.
 */
export function effectiveTicks(
  nodes: (Linked & { start_tick?: number | null })[],
  edges: Edge[],
): Map<string, number> {
  const { preds, succs } = adjacency(nodes, edges);
  const own = new Map(nodes.map((n) => [n.id, n.start_tick ?? null]));
  const order = topoOrder(nodes, edges, () => 0);
  const after = new Map<string, number | null>();
  for (const id of order) {
    after.set(id, own.get(id) ?? maxOf((preds.get(id) ?? []).map((p) => after.get(p))));
  }
  const before = new Map<string, number | null>();
  for (const id of [...order].reverse()) {
    before.set(id, own.get(id) ?? minOf((succs.get(id) ?? []).map((s) => before.get(s))));
  }
  const eff = new Map<string, number>();
  for (const n of nodes) {
    const lo = after.get(n.id) ?? null;
    const hi = before.get(n.id) ?? null;
    const mine = own.get(n.id);
    if (mine !== null && mine !== undefined) eff.set(n.id, mine);
    else if (lo !== null && hi !== null) eff.set(n.id, (lo + hi) / 2);
    else eff.set(n.id, lo ?? hi ?? Infinity);
  }
  return eff;
}

export function rowByNode(
  nodes: (Linked & { start_tick?: number | null })[],
  edges: Edge[],
): Map<string, number> {
  const eff = effectiveTicks(nodes, edges);
  const order = topoOrder(nodes, edges, (id) => eff.get(id) ?? Infinity);
  return new Map(order.map((id, index) => [id, index]));
}
