// Reading the book's report: narrowing it to one thread, counting it, and
// walking it one issue at a time in triage.
//
// Nothing here decides what is wrong. The grouping, wording, order and
// severity all arrive from the server, so the report and the timeline cannot
// call the same rule two different things; this only arranges what came.

import type { BookReport, Issue, IssueGroup } from "../api/types";

/** Issues about `thread` only. A book-wide issue is about no thread, so it stands down. */
export function narrow(groups: IssueGroup[], thread: string): IssueGroup[] {
  if (!thread) return groups;
  return groups
    .map((g) => ({
      ...g,
      issues: g.issues.filter((i) => i.plotlines.some((p) => p.id === thread)),
    }))
    .filter((g) => g.issues.length > 0);
}

export function count(
  groups: IssueGroup[],
  keep: (issue: Issue) => boolean = () => true,
): number {
  return groups.reduce((n, g) => n + g.issues.filter(keep).length, 0);
}

export interface Verdict {
  problems: number;
  undated: number;
}

/** The line read first, counted from what is on screen after any narrowing. */
export function verdict(problems: IssueGroup[], notes: IssueGroup[]): Verdict {
  return {
    problems: count(problems),
    undated: count(notes, (i) => i.code === "UNSCHEDULED"),
  };
}

/** A stable identity for an issue, so triage keeps its place across a re-check. */
export function issueKey(issue: Issue): string {
  const anchor = issue.scene?.id ?? issue.goal?.id ?? "";
  const others = [...issue.events.map((e) => e.id), ...issue.goals.map((g) => g.id)].join(
    ",",
  );
  const refs = issue.refs.map((r) => `${r.collection}/${r.id}`).join(",");
  return `${issue.code}|${anchor}|${others}|${refs}`;
}

/** Every issue in reading order -- problems first, then notes if they are showing. */
export function readingOrder(
  problems: IssueGroup[],
  notes: IssueGroup[],
  notesOpen: boolean,
): Issue[] {
  const all = [...problems, ...(notesOpen ? notes : [])];
  return all.flatMap((g) => g.issues);
}

/**
 * Where triage goes after the list changed under it: the same issue if it is
 * still there, else whatever now sits where it was -- the fix worked, so the
 * next one has moved up into its place.
 */
export function keepPlace(
  order: Issue[],
  previousKey: string | null,
  previousIndex: number,
): number {
  if (order.length === 0) return -1;
  if (previousKey !== null) {
    const found = order.findIndex((i) => issueKey(i) === previousKey);
    if (found >= 0) return found;
  }
  return Math.min(Math.max(previousIndex, 0), order.length - 1);
}

/** One step forward or back, stopping at the ends rather than wrapping. */
export function step(index: number, delta: number, length: number): number {
  if (length === 0) return -1;
  return Math.min(Math.max(index + delta, 0), length - 1);
}

/** Threads by how much is wrong on them, most first; the title breaks a tie. */
export function rollup(report: BookReport): BookReport["plotlines"] {
  return [...report.plotlines].sort(
    (a, b) => b.problems - a.problems || (a.title ?? a.id).localeCompare(b.title ?? b.id),
  );
}

/** The thread an issue is best opened on: the first it lands on, if any. */
export function homeThread(issue: Issue): string | null {
  return issue.plotlines[0]?.id ?? null;
}
