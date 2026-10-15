// Reading the server's verdicts on a thread. No rules live here: severity,
// wording and the problem count all arrive from the server, so the timeline,
// the editor and the preview say exactly the same thing. This only sorts out
// which mark goes where.

import type { EventSummary, PlotlineStatus } from "../../api/types";

export type Marker = "conflict" | "hint" | null;

export function hasConflict(scene: Pick<EventSummary, "findings">): boolean {
  return (scene.findings ?? []).some((f) => f.severity === "conflict");
}

/** The mark a rail dot or an editor row takes on, so a problem shows before it is read. */
export function markerOf(scene: Pick<EventSummary, "findings">): Marker {
  if (hasConflict(scene)) return "conflict";
  return (scene.findings ?? []).length ? "hint" : null;
}

export type Role = "terminus" | "merge" | "split" | null;

/** What a scene is in the weave, for the rail dot. */
export function roleOf(
  scene: Pick<EventSummary, "is_terminus" | "is_convergence" | "is_divergence">,
): Role {
  if (scene.is_terminus) return "terminus";
  if (scene.is_convergence) return "merge";
  if (scene.is_divergence) return "split";
  return null;
}

export function conflictCount(status: PlotlineStatus | undefined): number {
  return status?.conflicts ?? 0;
}

/** The scenes with something wrong, for the banner's list. */
export function problemScenes(events: EventSummary[]): EventSummary[] {
  return events.filter(hasConflict);
}

interface TerminusEvidence {
  terminus?: string;
  last_event?: string;
}

/**
 * Whole-thread verdicts no single scene can carry: a broken continuation, or a
 * thread that never reaches the book's ending. Ordering is left out -- it is
 * marked on the scenes themselves. The ending complaint only counts when the
 * book has an ending, or every thread would carry the same sentence.
 */
export function verdictNotes(
  status: PlotlineStatus | undefined,
  events: EventSummary[] = [],
): string[] {
  if (!status) return [];
  const notes: string[] = [];
  const continuation = status.continuation;
  if (continuation?.state === "conflicted" && continuation.message)
    notes.push(continuation.message);
  const terminus = status.ends_at_terminus as
    (PlotlineStatus["ends_at_terminus"] & { evidence?: TerminusEvidence }) | undefined;
  if (terminus?.state === "conflicted" && terminus.evidence?.terminus) {
    const lastId = terminus.evidence.last_event;
    const last = events.find((e) => e.id === lastId);
    notes.push(`${terminus.message ?? ""} It ends at '${last?.title ?? lastId}'.`.trim());
  }
  return notes;
}

/**
 * How many other threads this one meets on the way, not counting the ending:
 * every thread meets there by rule, so counting it would say "meets everything".
 */
export function meetCount(events: EventSummary[]): number {
  const others = new Set<string>();
  for (const e of events) {
    if (e.is_terminus) continue;
    for (const id of e.shared_with ?? []) others.add(id);
  }
  return others.size;
}

/** The "another thread meets here" hint on a scene, or null when there is none to give. */
export function meetHint(scene: EventSummary): string | null {
  if (scene.is_terminus) return null;
  if (scene.is_convergence) return "Threads join here";
  if (scene.is_divergence) return "A thread departs here";
  const shared = (scene.shared_with ?? []).length;
  if (!shared) return null;
  return `Shared with ${shared} other thread${shared === 1 ? "" : "s"}`;
}
