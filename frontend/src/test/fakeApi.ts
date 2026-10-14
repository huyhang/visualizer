// An in-memory ResearchApi that records what it was asked. Each method can be
// replaced per test; the defaults answer from the state given.

import type { ResearchApi } from "../api/ResearchApi";
import type { Draft, InboxRow, Job, NoteSummary } from "../api/types";
import { job as makeJob } from "./fixtures";

export interface FakeState {
  jobs: Job[];
  inbox: InboxRow[];
  drafts: Record<string, Draft>;
  notes: NoteSummary[];
}

export type Calls = { method: string; args: unknown[] }[];

export function fakeApi(
  state: Partial<FakeState> = {},
  overrides: Partial<ResearchApi> = {},
) {
  const data: FakeState = { jobs: [], inbox: [], drafts: {}, notes: [], ...state };
  const calls: Calls = [];
  const record =
    <A extends unknown[], R>(method: string, fn: (...args: A) => R) =>
    (...args: A): R => {
      calls.push({ method, args });
      return fn(...args);
    };
  const notFound = () =>
    Promise.reject(Object.assign(new Error("Not found"), { status: 404 }));

  const api: ResearchApi = {
    world: "song",
    availability: record("availability", async () => ({
      state: "ready" as const,
      can_submit: true,
      message: "Ready.",
      model: "fake-model",
      verifier: "up" as const,
      private: true,
    })),
    listJobs: record("listJobs", async () => data.jobs),
    getJob: record(
      "getJob",
      async (id: string) => data.jobs.find((j) => j.id === id) ?? notFound(),
    ),
    ask: record("ask", async (request) => {
      const created = makeJob({
        question: request.question,
        state: "queued",
        parent: request.parent ?? null,
      });
      data.jobs = [created, ...data.jobs];
      return created;
    }),
    approvePlan: record("approvePlan", async (id: string) => ({
      ...data.jobs.find((j) => j.id === id)!,
      state: "queued" as const,
    })),
    cancel: record("cancel", async (id: string) => ({
      ...data.jobs.find((j) => j.id === id)!,
      state: "cancelled" as const,
    })),
    inbox: record("inbox", async () => data.inbox),
    draft: record("draft", async (slug: string) => data.drafts[slug] ?? notFound()),
    refine: record("refine", async () => makeJob({ state: "queued" })),
    acceptDraft: record("acceptDraft", async (slug: string) => ({
      article: `research/${slug}`,
      sources: [],
      relinked: [],
    })),
    closeDraft: record("closeDraft", async () => undefined),
    discardDraft: record("discardDraft", async () => undefined),
    imagePreviewUrl: (slug, index) => `/preview/${slug}/${index}`,
    importImage: record("importImage", async (_slug: string, index: number) => ({
      id: `${String(index).padStart(32, "a")}`,
    })),
    listNotes: record("listNotes", async () => data.notes),
    getNote: record("getNote", async (slug: string) => ({
      id: slug,
      rev: 3,
      document: { title: "Tea", body: "What I knew." },
    })),
    saveNote: record("saveNote", async (request) => ({
      note: `research/${request.note ?? "new-note"}`,
      rev: 1,
      sources: [],
      relinked: [],
    })),
    articleUrl: ({ db, col, id }) => `/#/${db}/${col}/${id}`,
    ...overrides,
  };
  return { api, calls, data };
}
