// `LogosApi` over Logos's JSON routes, with the session cookie the page already
// holds. Every write to something that exists carries `If-Match` with the
// revision this page read, so a save that raced another tab is refused rather
// than silently winning. `fetch` is injected so request building is testable.

import type { ArticleRef } from "../doc/types";
import { LogosApiError } from "./errors";
import type { LogosApi, SectionAddress } from "./LogosApi";
import type { CoachReview, DraftListing, Entity, ReviewSummary } from "./types";

export interface HttpApiOptions {
  /** Where Logos is mounted: "" when it owns the origin, "/logos" behind the gateway. */
  base: string;
  /** Where Akasha's article editor is, for links out of the page. */
  akashaUrl: string;
  fetch?: typeof fetch;
}

const enc = encodeURIComponent;

interface CallOptions {
  body?: unknown;
  revision?: number;
  keepalive?: boolean;
}

export function createHttpApi(options: HttpApiOptions): LogosApi {
  const { base, akashaUrl } = options;
  const send = options.fetch ?? window.fetch.bind(window);

  async function call<T>(
    method: string,
    path: string,
    { body, revision, keepalive }: CallOptions = {},
  ) {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (revision !== undefined) headers["If-Match"] = `"${revision}"`;
    const response = await send(base + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      keepalive,
    });
    if (response.status === 204) return undefined as T;
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const retry = Number(response.headers?.get?.("Retry-After"));
      throw new LogosApiError(
        response.status,
        (payload && typeof payload.error === "string" && payload.error) ||
          `The server answered ${response.status}.`,
        (payload && typeof payload.code === "string" && payload.code) || null,
        Number.isFinite(retry) && retry > 0 ? retry : null,
      );
    }
    return payload as T;
  }

  const book = (b: string) => `/books/${enc(b)}`;
  const volume = (b: string, v: string) => `${book(b)}/volumes/${enc(v)}`;
  const section = (at: SectionAddress) =>
    `${volume(at.book, at.volume)}/sections/${enc(at.section)}`;
  const draft = (at: SectionAddress, d: string) => `${section(at)}/drafts/${enc(d)}`;
  const review = (at: SectionAddress, r: string) => `${section(at)}/reviews/${enc(r)}`;
  const issue = (at: SectionAddress, r: string, i: string) =>
    `${review(at, r)}/issues/${enc(i)}`;
  const page = (query: Record<string, string>) => `${base}/?${new URLSearchParams(query)}`;

  return {
    manuscript: (b) => call("GET", book(b)),
    section: (at) => call("GET", section(at)),
    createSection: (b, v, s, { kind, title }) =>
      call("POST", `${volume(b, v)}/sections/${enc(s)}`, {
        body: {
          kind,
          title,
          overview: "",
          event_ids: [],
          document: { version: 1, type: "doc", content: [] },
        },
      }),
    updateSectionTitle: (at, title, revision) =>
      call("PUT", `${section(at)}/metadata`, { body: { title }, revision }),

    drafts: (at) => call<DraftListing>("GET", `${section(at)}/drafts`),
    draft: (at, d) => call("GET", draft(at, d)),
    createDraft: (at, name, source) =>
      call("POST", `${section(at)}/drafts`, { body: { name, source } }),
    saveDraft: (at, d, body, revision, keepalive = false) =>
      call("PUT", draft(at, d), { body, revision, keepalive }),
    makePrimary: (at, d, revision) =>
      call("PUT", `${section(at)}/primary-draft`, { body: { draft: d }, revision }),

    entities: async (b, query) =>
      (
        await call<{ entities: Entity[] }>(
          "GET",
          `${book(b)}/ui/entities?${new URLSearchParams({ q: query })}`,
        )
      ).entities,
    coach: (b, document, dialect) =>
      call<CoachReview>("POST", `${book(b)}/ui/writing-review`, {
        body: { document, dialect },
      }),

    reviewAvailability: () => call("GET", "/llm-review/availability"),
    reviewReferences: (at, d, include) => {
      const query = new URLSearchParams({ draft: d });
      for (const ref of include) query.append("include", ref);
      return call("GET", `${section(at)}/reviews/references?${query}`);
    },
    askForReview: (at, request) =>
      call("POST", `${section(at)}/reviews`, { body: request }),
    reviews: async (at) =>
      (await call<{ reviews: ReviewSummary[] }>("GET", `${section(at)}/reviews`)).reviews,
    review: (at, r) => call("GET", review(at, r)),
    cancelReview: (at, r) => call("DELETE", review(at, r)),
    setIssueStatus: (at, r, i, status) =>
      call("PUT", issue(at, r, i), { body: { status } }),
    issue: (at, r, i) => call("GET", issue(at, r, i)),
    discuss: (at, r, i, text) =>
      call("POST", `${issue(at, r, i)}/messages`, { body: { text } }),

    articleUrl: ({ database, collection, id }: ArticleRef) => {
      const root = akashaUrl.endsWith("/") ? akashaUrl : `${akashaUrl}/`;
      return `${root}#/${[database, collection, id].map(enc).join("/")}`;
    },
    readerUrl: (at, block = null, d = null) =>
      page({
        book: at.book,
        volume: at.volume,
        section: at.section,
        ...(block ? { block } : {}),
        ...(d ? { draft: d } : {}),
      }),
    contentsUrl: (b) => page({ book: b }),
    writerUrl: (at, d = null) =>
      page({
        book: at.book,
        volume: at.volume,
        section: at.section,
        mode: "write",
        ...(d ? { draft: d } : {}),
      }),
  };
}
