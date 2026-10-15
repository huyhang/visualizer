// A thread's timeline as blocks: each period heading, then the run of scenes
// beneath it, so a period's rail connects and stops cleanly before the next.

import type { AxisItem } from "../timeaxis";

export type Section<T> =
  | { kind: "header"; level: number; label: string }
  | { kind: "rows"; depth: number; rows: { event: T; label: string }[] };

export function sections<T>(items: AxisItem<T>[]): Section<T>[] {
  const out: Section<T>[] = [];
  for (const item of items) {
    if (item.type === "header") {
      out.push({ kind: "header", level: item.level, label: item.label });
      continue;
    }
    const last = out[out.length - 1];
    if (last?.kind === "rows") last.rows.push({ event: item.event, label: item.label });
    else
      out.push({
        kind: "rows",
        depth: item.depth,
        rows: [{ event: item.event, label: item.label }],
      });
  }
  return out;
}
