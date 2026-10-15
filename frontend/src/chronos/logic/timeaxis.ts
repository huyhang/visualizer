// Grouping scenes under the book's own periods: a Year/Month/Day calendar
// nests Year -> Month headings with "Day, time" on each scene; a deeper
// calendar nests deeper; plain ticks or one cycle stay flat. Ported from the
// classic page's timeaxis.js. No formatting happens here -- the server's codec
// split each label already (`start_parts`), and this only reads the split.

export interface TimedScene {
  scheduled?: boolean | null;
  start_tick?: number | null;
  end_tick?: number | null;
  start_label?: string | null;
  end_label?: string | null;
  start_parts?: string[] | null;
  end_parts?: string[] | null;
}

export type AxisItem<T> =
  | { type: "header"; level: number; label: string }
  | { type: "event"; event: T; label: string; depth: number };

/** Whether every scene is placed on the clock: how the timeline's note is phrased. */
export function allScheduled(events: TimedScene[]): boolean {
  return (
    events.length > 0 &&
    events.every(
      (e) =>
        e.scheduled &&
        e.start_tick !== null &&
        e.start_tick !== undefined &&
        e.end_tick !== null &&
        e.end_tick !== undefined,
    )
  );
}

// Older responses carry only the label; split it as the codec would have.
const split = (label: string) => label.split(", ");
const startParts = (e: TimedScene) =>
  e.start_parts && e.start_parts.length ? e.start_parts : split(String(e.start_label));
const endParts = (e: TimedScene) =>
  e.end_parts && e.end_parts.length
    ? e.end_parts
    : e.end_label != null
      ? split(e.end_label)
      : null;

/** Where two coarse-to-fine lists first differ. */
export function firstDiff(a: readonly string[], b: readonly string[]): number {
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  return i;
}

/**
 * Scenes as period headings and rows, in order. Every component coarser than
 * the finest (cycle, clock) pair becomes a heading level; a span's end drops
 * what it shares with its start; an undated scene reads "unscheduled" under
 * whatever period is current.
 */
export function groupByPeriod<T extends TimedScene>(events: T[]): AxisItem<T>[] {
  const items: AxisItem<T>[] = [];
  let shown: string[] = [];
  for (const e of events) {
    if (!e.scheduled || e.start_label == null) {
      items.push({ type: "event", event: e, label: "unscheduled", depth: shown.length });
      continue;
    }
    const parts = startParts(e);
    const headers = parts.slice(0, -2);
    let label = parts.slice(-2).join(", ");
    const end = endParts(e);
    if (end && e.end_label !== e.start_label) {
      label += ` → ${end.slice(firstDiff(parts, end)).join(", ")}`;
    }
    for (let i = firstDiff(shown, headers); i < headers.length; i++) {
      items.push({ type: "header", level: i, label: headers[i] ?? "" });
    }
    shown = headers;
    items.push({ type: "event", event: e, label, depth: headers.length });
  }
  return items;
}
