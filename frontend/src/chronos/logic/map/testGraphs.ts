// Story graphs for the map's tests, the same books the classic page's
// test_graph_js.py draws, so the ported rules are held to the same cases.

import type { Graph, GraphNode } from "../../api/types";

function node(
  id: string,
  tick: number | null,
  parts: (t: number) => string[],
  terminus = false,
): GraphNode {
  return {
    id,
    title: id.toUpperCase(),
    start_tick: tick,
    end_tick: tick === null ? null : tick + 1,
    start_label: tick === null ? null : `Day ${tick}`,
    end_label: tick === null ? null : `Day ${tick + 1}`,
    start_parts: tick === null ? null : parts(tick),
    end_parts: tick === null ? null : parts(tick + 1),
    scheduled: tick !== null,
    is_convergence: false,
    is_divergence: false,
    is_terminus: terminus,
  };
}

export function graphOf(
  paths: Record<string, string[]>,
  ticks: Record<string, number | null>,
  terminus: string | null,
  parts: (t: number) => string[] = (t) => ["Year 1", "Spring", `Day ${t}`],
): Graph {
  return {
    nodes: Object.entries(ticks).map(([id, t]) => node(id, t, parts, id === terminus)),
    edges: Object.entries(paths).flatMap(([pid, path]) =>
      path.slice(1).map((to, i) => ({ from: path[i] ?? "", to, plotlines: [pid] })),
    ),
    plotlines: Object.entries(paths).map(([pid, path]) => ({
      id: pid,
      title: pid[0]?.toUpperCase() + pid.slice(1),
      events: path,
      continues_into: null,
      effective_events: path,
    })),
    convergence: [],
    divergence: [],
    terminus,
  };
}

/**
 *   alpha  a1 a2 a3 a4 -> j1 ------------> T     (a long solitary run, then a join)
 *   beta          j1 -> b1 b2 b3 -> j2 --> T     (meets alpha at j1, gamma at j2)
 *   gamma                     j2 -> c1 --> T
 *   delta  d1 d2 ------------------------> T     (meets nobody but the ending)
 *
 * Listed in a tangled order: beta is what alpha and gamma both meet, yet it
 * sits on the far side of gamma.
 */
export const PATHS = {
  alpha: ["a1", "a2", "a3", "a4", "j1", "T"],
  gamma: ["j2", "c1", "T"],
  beta: ["j1", "b1", "b2", "b3", "j2", "T"],
  delta: ["d1", "d2", "T"],
};
const TICKS = {
  a1: 0,
  a2: 10,
  a3: 20,
  a4: 30,
  j1: 40,
  b1: 50,
  b2: 60,
  b3: 70,
  j2: 80,
  c1: 90,
  d1: 5,
  d2: 15,
  T: 200,
};

export const fourThreads = () => graphOf(PATHS, TICKS, "T");

/** One thread carries an undated scene early on; another runs a year past the ending. */
export function drift(): Graph {
  const parts = (tick: number) => {
    const year = Math.floor(tick / 8640);
    const rest = tick % 8640;
    return [
      `Year ${year + 1}`,
      `Month ${Math.floor(rest / 720) + 1}`,
      `Day ${Math.floor((rest % 720) / 24) + 1}`,
    ];
  };
  return graphOf(
    { drifting: ["opens", "undated", "early", "ending"], long: ["opens", "next-year"] },
    { opens: 0, undated: null, early: 48, ending: 200, "next-year": 8664 },
    null,
    parts,
  );
}

/** Two threads holding different scenes at the same ticks. */
export const atOnce = () =>
  graphOf(
    { knight: ["open-a", "duel", "aftermath", "end"], spy: ["open-b", "betrayal", "end"] },
    { "open-a": 0, "open-b": 0, duel: 100, betrayal: 100, aftermath: 200, end: 300 },
    "end",
    (t) => ["Year 1", "Month 1", `Day ${Math.floor(t / 24) + 1}`],
  );

/** The arrangement cost the lane order minimises, recomputed independently. */
export function cost(
  order: string[],
  paths: Record<string, string[]>,
  terminus = "T",
): number {
  const where = new Map(order.map((id, i) => [id, i]));
  const events = new Map(
    Object.entries(paths).map(([id, p]) => [id, new Set(p.filter((e) => e !== terminus))]),
  );
  let total = 0;
  for (const one of order) {
    for (const other of order) {
      if (one >= other) continue;
      const shared = [...(events.get(one) ?? [])].filter((e) =>
        events.get(other)?.has(e),
      ).length;
      total += shared * Math.abs((where.get(one) ?? 0) - (where.get(other) ?? 0));
    }
  }
  return total;
}
