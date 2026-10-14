// Data shaped exactly like Akasha's answers, for tests to build on.

import type { Draft, InboxRow, Job } from "../api/types";

let n = 0;

export function job(overrides: Partial<Job> = {}): Job {
  n += 1;
  return {
    id: `rj_${String(n).padStart(16, "0")}`,
    world: "song",
    requester: "mara",
    question: "How was tea served in the Song dynasty?",
    state: "done",
    progress: null,
    error: null,
    created_at: `2026-10-13T10:${String(n % 60).padStart(2, "0")}:00+00:00`,
    updated_at: "2026-10-13T10:00:00+00:00",
    draft: null,
    review: null,
    accepted: null,
    verification: null,
    plan: null,
    refines: null,
    superseded_by: null,
    parent: null,
    notes: [],
    ...overrides,
  };
}

export function readyJob(slug: string, overrides: Partial<Job> = {}): Job {
  return job({
    draft: `research-inbox/${slug}`,
    review: "pending",
    verification: "checked",
    ...overrides,
  });
}

export function inboxRow(slug: string, jobId: string, title: string): InboxRow {
  return {
    draft: `research-inbox/${slug}`,
    title,
    question: "q",
    requester: "mara",
    job: jobId,
    created_at: "2026-10-13T10:00:00+00:00",
    verification: "checked",
    facts: 2,
    images: 1,
    refining: false,
  };
}

export const BODY = [
  "Tea was ground to powder and whisked [[research-inbox/museum-tea]].",
  "== Serving ==",
  "* Served in Jian ware bowls [[research-inbox/blog-tea]]",
  "* Prized for their dark glaze",
].join("\n");

export function draft(source: Job): Draft {
  return {
    draft: source.draft!,
    article: {
      id: source.draft!.split("/")[1]!,
      rev: 1,
      document: { title: "Song Tea", body: BODY, era: "Northern Song" },
    },
    job: source,
    facts: [
      {
        text: "Tea was whisked into a froth.",
        check: "supported",
        citations: [
          {
            source: "research-inbox/museum-tea",
            quote: "whisked until a white froth formed",
          },
        ],
      },
      {
        text: "Bowls were dark.",
        check: "partial",
        citations: [{ source: "research-inbox/blog-tea", quote: "the dark glaze" }],
      },
    ],
    dropped_facts: [{ text: "Tea came in bags.", reason: "unsupported" }],
    sources: [
      {
        key: "s1",
        ref: "research-inbox/museum-tea",
        url: "https://museum.example/tea",
        title: "Tea at the museum",
        new: true,
      },
      {
        key: "s2",
        ref: "research-inbox/blog-tea",
        url: "https://blog.example/tea",
        title: "A tea blog",
        new: true,
      },
    ],
    images: [
      {
        index: 0,
        url: "https://museum.example/bowl.jpg",
        caption: "A Jian bowl",
        license: "CC0",
        source: "research-inbox/museum-tea",
        imported: null,
      },
    ],
    verification: {
      status: "checked",
      model: "minicheck",
      reason: null,
      checked: 2,
      removed: 0,
    },
    links: [],
    refining: null,
  };
}
