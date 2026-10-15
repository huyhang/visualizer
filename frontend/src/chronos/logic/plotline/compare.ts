// Trying another order: two candidate orders for one thread, each judged by the
// server as saving it would judge it, read side by side. Nothing here judges a
// story -- the counts are the server's; this only lines them up so the writer
// can see which arrangement holds together better before saving either.

import type { PlotlinePreview } from "../../api/types";
import { hasConflict } from "./verdicts";

export interface OrderSummary {
  problems: number;
  /** Scenes with a contradiction on them, by id. */
  troubled: string[];
  /** Whether the order reaches the book's ending. */
  reachesEnding: boolean;
  /** Whether the continuation chain holds. */
  continuationHolds: boolean;
}

export function summarize(preview: PlotlinePreview): OrderSummary {
  const status = preview.status;
  return {
    problems: status.conflicts ?? 0,
    troubled: preview.effective_events.filter(hasConflict).map((e) => e.id),
    reachesEnding: status.ends_at_terminus?.state !== "conflicted",
    continuationHolds: status.continuation?.state !== "conflicted",
  };
}

export type Better = "A" | "B" | "even";

/**
 * Which order holds together better: fewer problems first, then reaching the
 * ending, then an unbroken continuation. "even" when nothing tells them apart.
 */
export function better(a: OrderSummary, b: OrderSummary): Better {
  if (a.problems !== b.problems) return a.problems < b.problems ? "A" : "B";
  if (a.reachesEnding !== b.reachesEnding) return a.reachesEnding ? "A" : "B";
  if (a.continuationHolds !== b.continuationHolds) return a.continuationHolds ? "A" : "B";
  return "even";
}

/** "2 problems", "No problems": one column's headline. */
export function headline(summary: OrderSummary): string {
  if (!summary.problems) return "No problems";
  return `${summary.problems} problem${summary.problems === 1 ? "" : "s"}`;
}

/** Positions where the two orders differ, for marking the rows that moved. */
export function movedPositions(a: readonly string[], b: readonly string[]): Set<string> {
  const moved = new Set<string>();
  const length = Math.max(a.length, b.length);
  for (let n = 0; n < length; n++)
    if (a[n] !== b[n] && b[n] !== undefined) moved.add(b[n] as string);
  return moved;
}
