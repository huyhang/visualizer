// The editor's review, in the writer's terms: which issues to draw in the
// prose, what fix each one offers now, where the editor stands after a
// discussion, and how often to ask the server how things are going.

import type {
  Availability,
  AvailabilityState,
  Check,
  CoachIssue,
  IssueStatus,
  Progress,
  ReviewIssue,
  ReviewState,
  ReviewSummary,
  Stance,
} from "../api/types";
import type { Annotation, Placement } from "../editor/annotations";

export const CHECKS: readonly Check[] = ["continuity", "anachronism", "prose"];

export const CHECK_LABELS: Record<Check, string> = {
  continuity: "Continuity",
  anachronism: "Anachronism",
  prose: "Prose",
};

export const CHECK_HINTS: Record<Check, string> = {
  continuity: "Against your canon in Akasha",
  anachronism: "Against verified research and the watchlist",
  prose: "Clarity, rhythm, redundancy",
};

export const editorAnnotationId = (issue: Pick<ReviewIssue, "id">) => `editor:${issue.id}`;
export const coachAnnotationId = (issue: Pick<CoachIssue, "id">) => `coach:${issue.id}`;

/** Open issues, drawn in the prose; dismissed and resolved ones are not. */
export function editorAnnotations(issues: ReviewIssue[]): Annotation[] {
  return issues
    .filter((issue) => issue.status === "open")
    .map((issue) => ({
      id: editorAnnotationId(issue),
      source: "editor" as const,
      kind: issue.check,
      severity: issue.severity,
      blockId: issue.block,
      quote: issue.quote,
    }));
}

/** Coach findings the writer has not set aside, drawn in the prose. */
export function coachAnnotations(issues: CoachIssue[]): Annotation[] {
  return issues.map((issue) => ({
    id: coachAnnotationId(issue),
    source: "coach" as const,
    kind: issue.category,
    severity: "info" as const,
    blockId: issue.block,
    quote: issue.excerpt,
  }));
}

export interface CurrentFix {
  suggestion: string | null;
  replacement: string | null;
  /** True when the fix comes from the editor revising itself in the discussion. */
  revised: boolean;
}

/** The fix an issue offers now: the editor's latest revision, else the review's own. */
export function currentFix(issue: ReviewIssue): CurrentFix {
  const revision = [...issue.discussion]
    .reverse()
    .find((turn) => turn.role === "editor" && turn.stance === "revises");
  if (revision) {
    return {
      suggestion: revision.suggestion,
      replacement: revision.replacement,
      revised: true,
    };
  }
  return { suggestion: issue.suggestion, replacement: issue.replacement, revised: false };
}

/** Where the editor stands after the discussion so far; null before it has replied. */
export function stanceOf(issue: ReviewIssue): Stance | null {
  const reply = [...issue.discussion].reverse().find((turn) => turn.role === "editor");
  return reply?.stance ?? null;
}

export const STANCE_LABELS: Record<Stance, string> = {
  maintains: "Maintains",
  revises: "Revises",
  withdraws: "Withdraws",
};

export const isActive = (state: ReviewState | undefined) =>
  state === "queued" || state === "running";
export const isReplying = (issue: ReviewIssue) => isActive(issue.reply?.state);

/** How long to wait before asking again: every few seconds while watched, rarely when not. */
export function pollDelay(active: boolean, visible: boolean): number | false {
  if (!active) return false;
  return visible ? 3000 : 30_000;
}

/** The review to show when the tab opens: the newest. */
export const latestReview = (reviews: ReviewSummary[]) => reviews[0] ?? null;

export type IssueFilter = "open" | "done" | "all";

const DONE: IssueStatus[] = ["dismissed", "resolved"];

/** Issues to list, in reading order: by block, then by where the quote sits. */
export function listedIssues(
  issues: ReviewIssue[],
  filter: IssueFilter,
  checks: readonly Check[],
  blockOrder: string[],
  placement: Placement,
): ReviewIssue[] {
  const order = new Map(blockOrder.map((id, index) => [id, index]));
  const wanted = issues.filter(
    (issue) =>
      checks.includes(issue.check) &&
      (filter === "all" ||
        (filter === "open" ? issue.status === "open" : DONE.includes(issue.status))),
  );
  const at = (issue: ReviewIssue) =>
    placement[editorAnnotationId(issue)]?.from ?? Number.MAX_SAFE_INTEGER;
  return wanted.sort(
    (a, b) =>
      (order.get(a.block) ?? Number.MAX_SAFE_INTEGER) -
        (order.get(b.block) ?? Number.MAX_SAFE_INTEGER) || at(a) - at(b),
  );
}

export function issueCounts(issues: ReviewIssue[]) {
  const counts = { open: 0, dismissed: 0, resolved: 0, total: issues.length };
  for (const issue of issues) counts[issue.status] += 1;
  return counts;
}

/** The issue `step` places after `current` in `listed`, wrapping round; the first if none. */
export function stepIssue(
  listed: ReviewIssue[],
  current: string | null,
  step: 1 | -1,
): ReviewIssue | null {
  if (!listed.length) return null;
  const at = listed.findIndex((issue) => issue.id === current);
  if (at < 0) return listed[step > 0 ? 0 : listed.length - 1] ?? null;
  return listed[(at + step + listed.length) % listed.length] ?? null;
}

export type Tone = "ok" | "warn" | "off" | "danger";

/** The status pill's colour for each state of the box. */
export function availabilityTone(state: AvailabilityState | undefined): Tone {
  switch (state) {
    case "ready":
      return "ok";
    case "cold":
    case "busy":
    case "queue_full":
    case "degraded":
      return "warn";
    case "misconfigured":
    case "incompatible":
      return "danger";
    default:
      return "off";
  }
}

const SHORT: Record<AvailabilityState, string> = {
  off: "Off",
  unreachable: "Asleep",
  misconfigured: "Misconfigured",
  incompatible: "Needs an update",
  degraded: "Degraded",
  queue_full: "Queue full",
  busy: "Busy",
  cold: "Warming up",
  ready: "Ready",
};

export const availabilityLabel = (availability: Availability | undefined) =>
  availability ? SHORT[availability.state] : "Checking…";

const STAGES: Record<string, string> = {
  loading_model: "Waking the editor",
  reviewing: "Reading the chapter",
  second_check: "Second-checking each issue",
  replying: "Writing a reply",
};

/** What the editor is doing, in a few words. */
export function stageLabel(state: ReviewState, progress: Progress | null): string {
  if (state === "queued") return "Waiting its turn";
  if (!progress) return "Starting";
  return STAGES[progress.stage] ?? progress.message ?? "Working";
}

/** The second-check line under a finished review. */
export function verificationLabel(summary: Pick<ReviewSummary, "verification">): string {
  const v = summary.verification;
  if (!v) return "";
  if (v.status === "checked") {
    return v.removed
      ? `Second-checked · ${v.removed} doubtful ${v.removed === 1 ? "issue" : "issues"} removed`
      : "Second-checked";
  }
  return v.status === "skipped"
    ? "First pass only · the second checker was away"
    : "First pass only";
}
