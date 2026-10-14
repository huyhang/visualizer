// How far a research job has got, for the stage timeline and for polling.

import type { Job } from "../api/types";

export interface Stage {
  key: string;
  label: string;
}

/** The worker's research stages, in the order it runs them. */
export const STAGES: Stage[] = [
  { key: "planning", label: "Planning searches" },
  { key: "searching", label: "Searching the web" },
  { key: "fetching", label: "Reading sources" },
  { key: "extracting", label: "Extracting facts" },
  { key: "verifying", label: "Checking every quote" },
  { key: "second_check", label: "Second check" },
  { key: "writing", label: "Writing the draft" },
];

export type StageState = "done" | "current" | "todo";

/**
 * Each stage's state. Before the first stage reports (queued, or loading the
 * model) nothing is current; once the job is importing, everything is done.
 * A stage the worker skipped (no verifier, so no second check) reads as done
 * once a later one starts.
 */
export function stageStates(job: Job): StageState[] {
  if (job.state === "importing" || job.state === "done") return STAGES.map(() => "done");
  const at = STAGES.findIndex((s) => s.key === job.progress?.stage);
  return STAGES.map((_, n) =>
    at === -1 ? "todo" : n < at ? "done" : n === at ? "current" : "todo",
  );
}

/** A line for the writer about what is happening before the stages begin. */
export function waitingLine(job: Job): string | null {
  if (job.state === "submitting") return "Sending the question to the GPU box…";
  if (job.state === "importing") return "Bringing the draft into your world…";
  if (job.progress?.stage === "loading_model")
    return "Loading the model — the first job takes a little longer.";
  if (job.state === "queued" || !job.progress)
    return "Waiting for its turn on the GPU box…";
  return null;
}

export const WATCHING_MS = 4_000;
export const BACKGROUND_MS = 30_000;

const POLLED = new Set(["submitting", "queued", "running", "importing"]);

/**
 * How often to ask about a job: every few seconds while the writer can see the
 * page, every half-minute when they cannot, and not at all once it has
 * settled. A job waiting for its plan only changes if the plan expires, so it
 * is asked about slowly either way.
 */
export function pollInterval(job: Job | undefined, visible: boolean): number | false {
  if (!job) return false;
  if (job.state === "awaiting_approval") return BACKGROUND_MS;
  if (!POLLED.has(job.state)) return false;
  return visible ? WATCHING_MS : BACKGROUND_MS;
}
