// Which column each thread gets. Ported from layout.js's lane ordering.
//
// The book's own (name) order is arbitrary with respect to who meets whom, so a
// book tangles as soon as it has a few threads. Two candidates -- the book's
// order, and one barycentre sweep away from it -- are each polished by
// adjacent swaps, and the cheaper wins with ties going to the book: so the
// result is deterministic and never worse than where it started. A thread's
// *column* moves only when the selection changes; its colour never does.

interface Lane {
  id: string;
  effective_events: string[];
}

/** How many scenes each pair of threads shares, the terminus excluded (everyone shares it). */
export function sharedCounts(
  lanes: Lane[],
  terminus: string | null,
): Map<number, number>[] {
  const sets = lanes.map((p) => new Set(p.effective_events.filter((e) => e !== terminus)));
  const weight = lanes.map(() => new Map<number, number>());
  for (let i = 0; i < lanes.length; i++) {
    for (let j = i + 1; j < lanes.length; j++) {
      let n = 0;
      for (const e of sets[i] ?? []) if (sets[j]?.has(e)) n++;
      if (n) {
        weight[i]?.set(j, n);
        weight[j]?.set(i, n);
      }
    }
  }
  return weight;
}

/** Every meeting pair, weighted by how often, times how many columns apart: short curves are cheap. */
export function arrangementCost(order: number[], weight: Map<number, number>[]): number {
  const pos = new Map(order.map((lane, column) => [lane, column]));
  let cost = 0;
  for (const lane of order) {
    for (const [other, w] of weight[lane] ?? []) {
      if (lane < other) cost += w * Math.abs((pos.get(lane) ?? 0) - (pos.get(other) ?? 0));
    }
  }
  return cost;
}

/** Move each thread to the weighted average column of those it meets, then re-sort. */
function barycentreSweep(order: number[], weight: Map<number, number>[]): number[] {
  const pos = new Map(order.map((lane, column) => [lane, column]));
  const bary = new Map(
    order.map((lane) => {
      let sum = 0;
      let total = 0;
      for (const [other, w] of weight[lane] ?? []) {
        sum += w * (pos.get(other) ?? 0);
        total += w;
      }
      return [lane, total ? sum / total : (pos.get(lane) ?? 0)];
    }),
  );
  return [...order].sort((a, b) => (bary.get(a) ?? 0) - (bary.get(b) ?? 0) || a - b);
}

/** Swap neighbours while it lowers the cost: monotonic, so it can only improve, and it ends. */
function polish(order: number[], weight: Map<number, number>[], rounds = 8): number[] {
  const out = [...order];
  const swap = (i: number) =>
    ([out[i], out[i + 1]] = [out[i + 1] as number, out[i] as number]);
  for (let round = 0; round < rounds; round++) {
    let moved = false;
    for (let i = 0; i + 1 < out.length; i++) {
      const before = arrangementCost(out, weight);
      swap(i);
      if (arrangementCost(out, weight) < before) moved = true;
      else swap(i);
    }
    if (!moved) break;
  }
  return out;
}

export function orderLanes<T extends Lane>(
  plotlines: T[],
  { terminus = null }: { terminus?: string | null } = {},
): T[] {
  const lanes = [...plotlines];
  if (lanes.length < 3) return lanes;
  const weight = sharedCounts(lanes, terminus);
  const book = lanes.map((_, i) => i);
  const candidates = [polish(book, weight), polish(barycentreSweep(book, weight), weight)];
  const best = candidates.reduce((a, b) =>
    arrangementCost(b, weight) < arrangementCost(a, weight) ? b : a,
  );
  return best.map((i) => lanes[i] as T);
}
