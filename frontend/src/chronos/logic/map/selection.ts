// Which threads the map shows, and what it says about that. Pure, so the
// picker's rules are testable without a browser.
//
// A selection worth a link rides in the URL as a list; the empty list means
// "all of them", so the plain map link means what it looks like it means.

import type { Graph } from "../../api/types";
import { connectedIds } from "./subgraph";

/** What the map opens on: the connected preset, else the URL's list, else everything. */
export function initialSelection(
  graph: Pick<Graph, "plotlines" | "terminus">,
  selection: string[],
  connectedFrom: string | null,
): Set<string> {
  const book = graph.plotlines.map((p) => p.id);
  const known = new Set(book);
  if (connectedFrom && known.has(connectedFrom)) return connectedIds(graph, connectedFrom);
  const asked = selection.filter((id) => known.has(id));
  return new Set(asked.length ? asked : book);
}

export function toggled(selected: Set<string>, id: string): Set<string> {
  const next = new Set(selected);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/** "Everything except these two" is a real way to read a book. */
export function inverted(bookOrder: string[], selected: Set<string>): Set<string> {
  return new Set(bookOrder.filter((id) => !selected.has(id)));
}

/** The list the URL carries: in book order, and empty when every thread is shown. */
export function urlSelection(bookOrder: string[], selected: Set<string>): string[] {
  if (selected.size === bookOrder.length && bookOrder.every((id) => selected.has(id)))
    return [];
  return bookOrder.filter((id) => selected.has(id));
}

/** Whether a thread's title holds every typed word. */
export function matchesFilter(title: string, query: string): boolean {
  const hay = title.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((w) => hay.includes(w));
}

/** Every thread through each drawn node, so hovering a thread can light up its whole path. */
export function threadsByNode(
  plotlines: { id: string; effective_events: string[] }[],
): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>();
  for (const p of plotlines) {
    for (const e of p.effective_events) out.set(e, new Set([...(out.get(e) ?? []), p.id]));
  }
  return out;
}

/** The line under the drawing: what is folded, what the underline means, what has no time. */
export function footnote({
  folded,
  hidden,
  hasTerminus,
  hasUnscheduled,
}: {
  folded: number;
  hidden: number;
  hasTerminus: boolean;
  hasUnscheduled: boolean;
}): string {
  return [
    hidden
      ? `${hidden} scenes are folded into ${folded} solitary stretch${folded === 1 ? "" : "es"} — unfold one to see them.`
      : "",
    hasTerminus
      ? "The underlined scene is this book's ending — every thread must reach it."
      : "",
    hasUnscheduled
      ? "Some scenes have no timing yet; they sit between the dated scenes either side of them."
      : "",
  ]
    .filter(Boolean)
    .join(" ");
}
