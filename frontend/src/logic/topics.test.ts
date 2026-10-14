import { describe, expect, it } from "vitest";
import type { Job } from "../api/types";
import { inboxRow, job, readyJob } from "../test/fixtures";
import {
  buildTopicTree,
  countTopics,
  findTopic,
  live,
  mergeJob,
  pathTo,
  topicStatus,
  type TopicStatus,
} from "./topics";

describe("topicStatus", () => {
  it.each<[Partial<Job>, TopicStatus]>([
    [{ state: "queued" }, "researching"],
    [{ state: "submitting" }, "researching"],
    [{ state: "running" }, "researching"],
    [{ state: "importing" }, "researching"],
    [{ state: "awaiting_approval" }, "needs-approval"],
    [{ state: "failed" }, "failed"],
    [{ state: "done", review: "pending" }, "ready"],
    [{ state: "done", review: "done", notes: ["research/tea"] }, "saved"],
    [{ state: "done", review: "accepted", accepted: "research/tea" }, "saved"],
    [{ state: "done", review: "done" }, "closed"],
  ])("%j -> %s", (fields, expected) => {
    expect(topicStatus(job(fields))).toBe(expected);
  });
});

const ids = (nodes: ReturnType<typeof buildTopicTree>): unknown[] =>
  nodes.map((n) => (n.children.length ? [n.job.id, ids(n.children)] : n.job.id));

describe("buildTopicTree", () => {
  it("puts digging deeper under its parent, newest roots first, children oldest first", () => {
    const root = readyJob("tea", { created_at: "2026-10-13T10:00:00Z" });
    const other = job({ state: "running", created_at: "2026-10-13T12:00:00Z" });
    const first = job({
      parent: root.id,
      state: "running",
      created_at: "2026-10-13T10:10:00Z",
    });
    const second = job({
      parent: root.id,
      state: "queued",
      created_at: "2026-10-13T10:20:00Z",
    });
    expect(ids(buildTopicTree([second, other, first, root]))).toEqual([
      other.id,
      [root.id, [first.id, second.id]],
    ]);
  });

  it.each<[string, Partial<Job>]>([
    ["cancelled", { state: "cancelled" }],
    ["rejected", { review: "rejected", state: "done" }],
    ["superseded", { review: "superseded", state: "done" }],
  ])("hides a %s job", (_, fields) => {
    expect(buildTopicTree([job(fields)])).toEqual([]);
  });

  it("titles a topic by its draft once there is one", () => {
    const ready = readyJob("song-tea");
    const [node] = buildTopicTree([ready], [inboxRow("song-tea", ready.id, "Song Tea")]);
    expect(node!.title).toBe("Song Tea");
    expect(buildTopicTree([job({ question: "Q?" })])[0]!.title).toBe("Q?");
  });

  it.each<[string, Partial<Job>]>([
    ["under way", { state: "running" }],
    ["waiting for its plan", { state: "awaiting_approval" }],
    ["failed", { state: "failed" }],
    ["imported but not yet settled", { state: "done", review: null }],
  ])("a refinement %s is part of the topic it steers", (_, fields) => {
    const original = readyJob("tea");
    const steering = job({ refines: "research-inbox/tea", ...fields });
    const tree = buildTopicTree([steering, original]);
    expect(ids(tree)).toEqual([original.id]);
    expect(tree[0]!.refinement?.id).toBe(steering.id);
  });

  it("a cancelled refinement leaves its topic as it was", () => {
    const original = readyJob("tea");
    const cancelled = job({ refines: "research-inbox/tea", state: "cancelled" });
    const tree = buildTopicTree([cancelled, original]);
    expect(ids(tree)).toEqual([original.id]);
    expect(tree[0]!.refinement).toBeNull();
  });

  it("a refinement that replaced its draft carries the topic, and its children", () => {
    const original = readyJob("tea", { review: "superseded" });
    const refined = readyJob("tea", {
      refines: "research-inbox/tea",
      created_at: "2026-10-13T11:00:00Z",
    });
    original.superseded_by = refined.id;
    const child = job({ parent: original.id, state: "running" });
    expect(ids(buildTopicTree([refined, child, original]))).toEqual([
      [refined.id, [child.id]],
    ]);
  });

  it("a refinement that arrived as a draft of its own is a topic of its own", () => {
    const accepted = job({ draft: null, review: "accepted", accepted: "research/tea" });
    const separate = readyJob("tea-2", { refines: "research-inbox/tea" });
    expect(ids(buildTopicTree([separate, accepted]))).toHaveLength(2);
  });

  it("a child whose parent is hidden or missing becomes a root", () => {
    const gone = job({ state: "cancelled" });
    const child = job({ parent: gone.id, state: "running" });
    const orphan = job({ parent: "rj_ffffffffffffffff", state: "running" });
    expect(ids(buildTopicTree([gone, child, orphan])).sort()).toEqual(
      [child.id, orphan.id].sort(),
    );
  });
});

describe("live", () => {
  it("follows superseded_by to the job a topic now lives on, and survives a loop", () => {
    const a = job(),
      b = job(),
      c = job();
    a.superseded_by = b.id;
    b.superseded_by = c.id;
    const byId = new Map([a, b, c].map((j) => [j.id, j]));
    expect(live(a.id, byId)).toBe(c.id);
    c.superseded_by = a.id;
    expect([a.id, b.id, c.id]).toContain(live(a.id, byId));
  });
});

describe("finding and walking", () => {
  const root = readyJob("tea");
  const child = job({ parent: root.id, state: "running" });
  const tree = buildTopicTree([child, root]);

  it.each([
    [child.id, child.id],
    ["nope", null],
    [null, null],
  ])("findTopic(%s)", (id, expected) => {
    expect(findTopic(tree, id)?.job.id ?? null).toBe(expected);
  });

  it("pathTo leads from the root down", () => {
    expect(pathTo(tree, child.id).map((n) => n.job.id)).toEqual([root.id, child.id]);
    expect(countTopics(tree)).toBe(2);
  });
});

describe("mergeJob", () => {
  it.each([
    ["replaces a known job in place", true],
    ["adds an unknown one first", false],
  ])("%s", (_, known) => {
    const a = job(),
      b = job();
    const fresh = known ? { ...b, state: "failed" as const } : job();
    const merged = mergeJob([a, b], fresh);
    expect(merged).toEqual(known ? [a, fresh] : [fresh, a, b]);
  });
});
