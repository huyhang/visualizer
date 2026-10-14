// Research jobs, seen as topics: a tree of the questions a world has asked.
//
// A topic is a job the writer would recognise as a question of theirs. A
// refinement under way is not a topic of its own -- it is the topic it steers,
// "being steered" -- and once it replaces its draft the old job is superseded
// and the refinement carries the topic on. "Dig deeper" makes a child: the new
// job's `parent` names the job it grew from, which may since have been
// superseded, so parents are followed along `superseded_by` to the live one.

import type { InboxRow, Job, JobState } from "../api/types";

export type TopicStatus =
  "researching" | "needs-approval" | "ready" | "failed" | "saved" | "closed";

export interface TopicNode {
  job: Job;
  title: string;
  status: TopicStatus;
  /** A refinement of this topic's draft that has not replaced it (yet). */
  refinement: Job | null;
  children: TopicNode[];
}

const ACTIVE: ReadonlySet<JobState> = new Set([
  "submitting",
  "queued",
  "running",
  "awaiting_approval",
  "importing",
]);

export function isActive(job: Job): boolean {
  return ACTIVE.has(job.state);
}

export function topicStatus(job: Job): TopicStatus {
  if (job.state === "awaiting_approval") return "needs-approval";
  if (isActive(job)) return "researching";
  if (job.state === "failed") return "failed";
  if (job.review === "pending") return "ready";
  return job.notes.length || job.accepted ? "saved" : "closed";
}

/**
 * Whether a job is a refinement still attached to the draft it steers. A
 * cancelled one steers nothing: the draft is as it was.
 */
function steers(job: Job, pendingDrafts: Set<string>): boolean {
  if (!job.refines || !pendingDrafts.has(job.refines)) return false;
  if (job.state === "cancelled") return false;
  return job.state !== "done" || job.review === null;
}

function hidden(job: Job): boolean {
  return (
    job.state === "cancelled" || job.review === "superseded" || job.review === "rejected"
  );
}

export function buildTopicTree(jobs: Job[], inbox: InboxRow[] = []): TopicNode[] {
  const byId = new Map(jobs.map((job) => [job.id, job]));
  const titles = new Map(inbox.map((row) => [row.draft, row.title]));
  const pendingDrafts = new Set(
    jobs.filter((j) => j.review === "pending" && j.draft).map((j) => j.draft!),
  );

  const refinements = new Map<string, Job>();
  for (const job of jobs) {
    if (steers(job, pendingDrafts) && !refinements.has(job.refines!)) {
      refinements.set(job.refines!, job); // newest first: the first seen is current
    }
  }

  const nodes = new Map<string, TopicNode>();
  for (const job of jobs) {
    if (hidden(job) || steers(job, pendingDrafts)) continue;
    nodes.set(job.id, {
      job,
      title: (job.draft && titles.get(job.draft)) || job.question,
      status: topicStatus(job),
      refinement: (job.draft && refinements.get(job.draft)) || null,
      children: [],
    });
  }

  const roots: TopicNode[] = [];
  for (const node of nodes.values()) {
    const parent = node.job.parent ? nodes.get(live(node.job.parent, byId)) : undefined;
    if (parent && parent !== node) parent.children.push(node);
    else roots.push(node);
  }
  roots.sort(newestFirst);
  for (const node of nodes.values()) node.children.sort((a, b) => -newestFirst(a, b));
  return roots;
}

/** The job a topic now lives on, following refinements that replaced it. */
export function live(id: string, byId: Map<string, Job>): string {
  const seen = new Set<string>();
  let current = id;
  while (!seen.has(current)) {
    seen.add(current);
    const next = byId.get(current)?.superseded_by;
    if (!next || !byId.has(next)) break;
    current = next;
  }
  return current;
}

function newestFirst(a: TopicNode, b: TopicNode): number {
  return b.job.created_at.localeCompare(a.job.created_at);
}

export function findTopic(nodes: TopicNode[], id: string | null): TopicNode | null {
  if (!id) return null;
  for (const node of nodes) {
    if (node.job.id === id) return node;
    const found = findTopic(node.children, id);
    if (found) return found;
  }
  return null;
}

/** The path from a root down to `id`, for a breadcrumb. */
export function pathTo(nodes: TopicNode[], id: string): TopicNode[] {
  for (const node of nodes) {
    if (node.job.id === id) return [node];
    const below = pathTo(node.children, id);
    if (below.length) return [node, ...below];
  }
  return [];
}

/** `jobs` with one replaced by its fresher copy (or added, newest first). */
export function mergeJob(jobs: Job[], job: Job): Job[] {
  const at = jobs.findIndex((j) => j.id === job.id);
  if (at === -1) return [job, ...jobs];
  const copy = jobs.slice();
  copy[at] = job;
  return copy;
}

export function countTopics(nodes: TopicNode[]): number {
  return nodes.reduce((n, node) => n + 1 + countTopics(node.children), 0);
}
