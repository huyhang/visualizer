import { vi } from "vitest";
import { LogosApiError } from "./errors";
import { createHttpApi } from "./http";
import type { LogosApi } from "./LogosApi";

const AT = { book: "ember pact", volume: "one", section: "the/gate" };
const DOC = { version: 1 as const, type: "doc" as const, content: [] };

function recording(status = 200, body: unknown = {}, headers: Record<string, string> = {}) {
  const fetch = vi.fn(async (_url: string, _init?: RequestInit) => ({
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
  })) as unknown as typeof window.fetch & ReturnType<typeof vi.fn>;
  const api = createHttpApi({ base: "/logos", akashaUrl: "/akasha", fetch });
  return { api, fetch };
}

describe("createHttpApi", () => {
  it.each<
    [
      string,
      (api: LogosApi) => Promise<unknown>,
      string,
      string,
      unknown,
      string | undefined,
    ]
  >([
    [
      "the manuscript",
      (a) => a.manuscript("ember pact"),
      "GET",
      "/logos/books/ember%20pact",
      undefined,
      undefined,
    ],
    [
      "a draft",
      (a) => a.draft(AT, "d1"),
      "GET",
      "/logos/books/ember%20pact/volumes/one/sections/the%2Fgate/drafts/d1",
      undefined,
      undefined,
    ],
    [
      "a save, guarded by the revision it read",
      (a) => a.saveDraft(AT, "d1", { name: "Draft", document: DOC }, 7),
      "PUT",
      "/logos/books/ember%20pact/volumes/one/sections/the%2Fgate/drafts/d1",
      { name: "Draft", document: DOC },
      '"7"',
    ],
    [
      "a title, guarded by the section's revision",
      (a) => a.updateSectionTitle(AT, null, 4),
      "PUT",
      "/logos/books/ember%20pact/volumes/one/sections/the%2Fgate/metadata",
      { title: null },
      '"4"',
    ],
    [
      "making a draft primary",
      (a) => a.makePrimary(AT, "d2", 9),
      "PUT",
      "/logos/books/ember%20pact/volumes/one/sections/the%2Fgate/primary-draft",
      { draft: "d2" },
      '"9"',
    ],
    [
      "the Coach",
      (a) => a.coach("ember pact", DOC, "en-GB"),
      "POST",
      "/logos/books/ember%20pact/ui/writing-review",
      { document: DOC, dialect: "en-GB" },
      undefined,
    ],
    [
      "availability",
      (a) => a.reviewAvailability(),
      "GET",
      "/logos/llm-review/availability",
      undefined,
      undefined,
    ],
    [
      "asking for a review",
      (a) => a.askForReview(AT, { draft: "d1", checks: ["prose"] }),
      "POST",
      "/logos/books/ember%20pact/volumes/one/sections/the%2Fgate/reviews",
      { draft: "d1", checks: ["prose"] },
      undefined,
    ],
    [
      "what a review would read, with articles added",
      (a) => a.reviewReferences(AT, "d1", ["w/c/a", "w/c/b"]),
      "GET",
      "/logos/books/ember%20pact/volumes/one/sections/the%2Fgate/reviews/references?draft=d1&include=w%2Fc%2Fa&include=w%2Fc%2Fb",
      undefined,
      undefined,
    ],
    [
      "an issue's status",
      (a) => a.setIssueStatus(AT, "r1", "i2", "dismissed"),
      "PUT",
      "/logos/books/ember%20pact/volumes/one/sections/the%2Fgate/reviews/r1/issues/i2",
      { status: "dismissed" },
      undefined,
    ],
    [
      "a message to the editor",
      (a) => a.discuss(AT, "r1", "i2", "Why?"),
      "POST",
      "/logos/books/ember%20pact/volumes/one/sections/the%2Fgate/reviews/r1/issues/i2/messages",
      { text: "Why?" },
      undefined,
    ],
    [
      "cancelling",
      (a) => a.cancelReview(AT, "r1"),
      "DELETE",
      "/logos/books/ember%20pact/volumes/one/sections/the%2Fgate/reviews/r1",
      undefined,
      undefined,
    ],
  ])("builds %s", async (_name, call, method, url, body, ifMatch) => {
    const { api, fetch } = recording();
    await call(api);
    const [sent, init] = fetch.mock.calls[0]!;
    expect(sent).toBe(url);
    expect(init?.method).toBe(method);
    expect(init?.body === undefined ? undefined : JSON.parse(init.body as string)).toEqual(
      body,
    );
    expect((init?.headers as Record<string, string>)["If-Match"]).toBe(ifMatch);
  });

  it("sends an urgent save with keepalive, so it survives the page closing", async () => {
    const { api, fetch } = recording();
    await api.saveDraft(AT, "d1", { name: "Draft", document: DOC }, 1, true);
    expect(fetch.mock.calls[0]![1]?.keepalive).toBe(true);
  });

  it("turns a refusal into an error carrying its status, code and Retry-After", async () => {
    const { api } = recording(
      429,
      { error: "Too many reviews.", code: "LLM_REVIEW_BUSY" },
      { "Retry-After": "30" },
    );
    const error = await api.askForReview(AT, {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(LogosApiError);
    expect(error).toMatchObject({
      status: 429,
      message: "Too many reviews.",
      code: "LLM_REVIEW_BUSY",
      retryAfter: 30,
      isBusy: true,
    });
  });

  it.each<[string, string]>([
    ["/akasha", "/akasha/#/ember/characters/lin%20qingyu"],
    ["/akasha/", "/akasha/#/ember/characters/lin%20qingyu"],
  ])("links an article out to Akasha at %s", (akashaUrl, expected) => {
    const api = createHttpApi({
      base: "",
      akashaUrl,
      fetch: vi.fn() as unknown as typeof fetch,
    });
    expect(
      api.articleUrl({ database: "ember", collection: "characters", id: "lin qingyu" }),
    ).toBe(expected);
  });

  it("names the reader, the contents and the writer the way the reader's own links do", () => {
    const { api } = recording();
    expect(api.readerUrl(AT, "p3", "d2")).toBe(
      "/logos/?book=ember+pact&volume=one&section=the%2Fgate&block=p3&draft=d2",
    );
    expect(api.contentsUrl("ember pact")).toBe("/logos/?book=ember+pact");
    expect(api.writerUrl(AT)).toBe(
      "/logos/?book=ember+pact&volume=one&section=the%2Fgate&mode=write",
    );
  });
});
