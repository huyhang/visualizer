import { describe, expect, it } from "vitest";
import { ApiError, isNoAccess, messageOf } from "./errors";
import { createHttpApi } from "./http";

type Sent = { url: string; init: RequestInit };

function fakeFetch(answers: Record<string, { status?: number; body?: unknown }>) {
  const sent: Sent[] = [];
  const fetch = (async (url: string, init: RequestInit) => {
    sent.push({ url, init });
    const key = Object.keys(answers).find((k) => url.endsWith(k)) ?? "";
    const { status = 200, body = {} } = answers[key] ?? {
      status: 404,
      body: { error: "No such route." },
    };
    return new Response(status === 204 ? null : JSON.stringify(body), { status });
  }) as unknown as typeof globalThis.fetch;
  return { fetch, sent };
}

const make = (answers: Record<string, { status?: number; body?: unknown }>) => {
  const { fetch, sent } = fakeFetch(answers);
  return {
    api: createHttpApi({
      apiRoot: "/akasha",
      akashaRoot: "/akasha/",
      world: "song dynasty",
      fetch,
    }),
    sent,
  };
};

describe("createHttpApi", () => {
  it.each<
    [string, (api: ReturnType<typeof make>["api"]) => Promise<unknown>, string, string]
  >([
    ["availability", (api) => api.availability(), "GET", "/akasha/research/availability"],
    [
      "listJobs",
      (api) => api.listJobs(),
      "GET",
      "/akasha/databases/song%20dynasty/research/jobs?limit=200",
    ],
    [
      "getJob",
      (api) => api.getJob("rj_1"),
      "GET",
      "/akasha/databases/song%20dynasty/research/jobs/rj_1",
    ],
    [
      "ask",
      (api) => api.ask({ question: "Tea?" }),
      "POST",
      "/akasha/databases/song%20dynasty/research/jobs",
    ],
    [
      "approvePlan",
      (api) => api.approvePlan("rj_1", []),
      "POST",
      "/akasha/databases/song%20dynasty/research/jobs/rj_1/plan",
    ],
    [
      "cancel",
      (api) => api.cancel("rj_1"),
      "DELETE",
      "/akasha/databases/song%20dynasty/research/jobs/rj_1",
    ],
    [
      "draft",
      (api) => api.draft("tea"),
      "GET",
      "/akasha/databases/song%20dynasty/research/inbox/tea",
    ],
    [
      "refine",
      (api) => api.refine("tea", { feedback: "f" }),
      "POST",
      "/akasha/databases/song%20dynasty/research/inbox/tea/refine",
    ],
    [
      "acceptDraft",
      (api) => api.acceptDraft("tea"),
      "POST",
      "/akasha/databases/song%20dynasty/research/inbox/tea/accept",
    ],
    [
      "closeDraft",
      (api) => api.closeDraft("tea"),
      "POST",
      "/akasha/databases/song%20dynasty/research/inbox/tea/done",
    ],
    [
      "discardDraft",
      (api) => api.discardDraft("tea"),
      "POST",
      "/akasha/databases/song%20dynasty/research/inbox/tea/reject",
    ],
    [
      "importImage",
      (api) => api.importImage("tea", 2),
      "POST",
      "/akasha/databases/song%20dynasty/research/inbox/tea/images/2/import",
    ],
    [
      "getNote",
      (api) => api.getNote("tea"),
      "GET",
      "/akasha/databases/song%20dynasty/collections/research/documents/tea",
    ],
    [
      "saveNote",
      (api) => api.saveNote({ title: "T", body: "B" }),
      "POST",
      "/akasha/databases/song%20dynasty/research/notes",
    ],
  ])("%s", async (_, act, method, url) => {
    const { api, sent } = make({
      [url.split("?")[0]!.replace("/akasha", "")]: { body: { jobs: [], drafts: [] } },
      "": {},
    });
    await act(api).catch(() => undefined);
    expect(sent[0]).toMatchObject({ url, init: { method } });
  });

  it("sends a body as JSON", async () => {
    const { api, sent } = make({ "/research/jobs": { status: 202, body: {} } });
    await api.ask({ question: "Tea?", parent: "rj_1" });
    expect(sent[0]!.init.body).toBe('{"question":"Tea?","parent":"rj_1"}');
    expect((sent[0]!.init.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
  });

  it("turns an error answer into an ApiError with Akasha's sentence", async () => {
    const { api } = make({
      "/research/notes": { status: 409, body: { error: "This note was changed." } },
    });
    const error = await api.saveNote({ title: "T", body: "B" }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect([error.status, error.isConflict, messageOf(error)]).toEqual([
      409,
      true,
      "This note was changed.",
    ]);
  });

  it("a 204 is nothing", async () => {
    const { api } = make({ "/done": { status: 204 } });
    await expect(api.closeDraft("tea")).resolves.toBeUndefined();
  });

  it.each([
    [[{ name: "characters" }], 1, []],
    [[{ name: "research" }], 2, [{ id: "tea", title: "Tea", rev: 2, updated: null }]],
  ])(
    "lists notes only when the world has a research category (%#)",
    async (collections, requests, expected) => {
      const { api, sent } = make({
        "/collections": { body: { collections } },
        "/documents?per_page=100": {
          body: {
            documents: [{ id: "tea", title: "Tea", rev: 2, updated: null, extra: 1 }],
          },
        },
      });
      expect(await api.listNotes()).toEqual(expected);
      expect(sent).toHaveLength(requests);
    },
  );

  it("builds links and preview URLs without a request", () => {
    const { api, sent } = make({});
    expect(api.articleUrl({ db: "song", col: "research", id: "tea bowls" })).toBe(
      "/akasha/#/song/research/tea%20bowls",
    );
    expect(api.imagePreviewUrl("tea", 1)).toBe(
      "/akasha/databases/song%20dynasty/research/inbox/tea/images/1?size=preview",
    );
    expect(sent).toEqual([]);
  });
});

describe("messageOf", () => {
  it.each([
    [new ApiError(400, "Bad."), "Bad."],
    [new Error("Broke."), "Broke."],
    ["what", "Something went wrong."],
    [
      new ApiError(403, "You do not have 'write' permission on this resource."),
      "You need write access to this world's research for that. Ask the world's owner to share it with you.",
    ],
    [
      new ApiError(403, "Forbidden."),
      "You need access to this world's research for that. Ask the world's owner to share it with you.",
    ],
  ])("%#", (error, expected) => {
    expect(messageOf(error)).toBe(expected);
  });
});

describe("isNoAccess", () => {
  it.each<[unknown, boolean]>([
    [new ApiError(403, "No."), true],
    [new ApiError(404, "No such world."), true],
    [new ApiError(503, "Asleep."), false],
    [new Error("Network."), false],
    [null, false],
  ])("%#", (error, expected) => {
    expect(isNoAccess(error)).toBe(expected);
  });
});
