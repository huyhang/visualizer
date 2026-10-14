// `ResearchApi` over Akasha's JSON routes, with the session cookie the page
// already holds. `fetch` is injected so the request building can be tested
// without a server.

import { ApiError } from "./errors";
import type { ResearchApi } from "./ResearchApi";
import type { DocumentResult, InboxRow, Job, NoteSummary } from "./types";

export interface HttpApiOptions {
  /** Where Akasha's API is mounted: "" at the origin root. */
  apiRoot: string;
  /** Where Akasha's article editor is, for links out of the studio. */
  akashaRoot: string;
  world: string;
  fetch?: typeof fetch;
}

const RESEARCH_NOTES = "research";
const NOTES_PAGE = 100;

export function createHttpApi(options: HttpApiOptions): ResearchApi {
  const { apiRoot, akashaRoot, world } = options;
  const send = options.fetch ?? window.fetch.bind(window);
  const enc = encodeURIComponent;
  const base = `${apiRoot}/databases/${enc(world)}`;
  const research = `${base}/research`;
  const draftPath = (slug: string) => `${research}/inbox/${enc(slug)}`;

  async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
    const init: RequestInit = { method, headers: { Accept: "application/json" } };
    if (body !== undefined) {
      init.headers = { ...init.headers, "Content-Type": "application/json" };
      init.body = JSON.stringify(body);
    }
    const response = await send(url, init);
    if (response.status === 204) return undefined as T;
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const message =
        (payload && typeof payload.error === "string" && payload.error) ||
        `The server answered ${response.status}.`;
      throw new ApiError(response.status, message);
    }
    return payload as T;
  }

  return {
    world,
    availability: () => call("GET", `${apiRoot}/research/availability`),
    listJobs: async (limit = 200) =>
      (await call<{ jobs: Job[] }>("GET", `${research}/jobs?limit=${limit}`)).jobs,
    getJob: (id) => call("GET", `${research}/jobs/${enc(id)}`),
    ask: (request) => call("POST", `${research}/jobs`, request),
    approvePlan: (id, queries) =>
      call("POST", `${research}/jobs/${enc(id)}/plan`, { queries }),
    cancel: (id) => call("DELETE", `${research}/jobs/${enc(id)}`),
    inbox: async () =>
      (await call<{ drafts: InboxRow[] }>("GET", `${research}/inbox`)).drafts,
    draft: (slug) => call("GET", draftPath(slug)),
    refine: (slug, request) => call("POST", `${draftPath(slug)}/refine`, request),
    acceptDraft: (slug) => call("POST", `${draftPath(slug)}/accept`),
    closeDraft: (slug) => call("POST", `${draftPath(slug)}/done`),
    discardDraft: (slug) => call("POST", `${draftPath(slug)}/reject`),
    imagePreviewUrl: (slug, index) => `${draftPath(slug)}/images/${index}?size=preview`,
    importImage: (slug, index) => call("POST", `${draftPath(slug)}/images/${index}/import`),
    listNotes: async () => {
      // Asked first, so a world with no research category yet costs no 404.
      const { collections } = await call<{ collections: { name: string }[] }>(
        "GET",
        `${base}/collections`,
      );
      if (!collections.some((c) => c.name === RESEARCH_NOTES)) return [];
      const page = await call<{ documents: NoteSummary[] }>(
        "GET",
        `${base}/collections/${RESEARCH_NOTES}/documents?per_page=${NOTES_PAGE}`,
      );
      return page.documents.map(({ id, title, rev, updated }) => ({
        id,
        title,
        rev,
        updated,
      }));
    },
    getNote: (slug) =>
      call<DocumentResult>(
        "GET",
        `${base}/collections/${RESEARCH_NOTES}/documents/${enc(slug)}`,
      ),
    saveNote: (request) => call("POST", `${research}/notes`, request),
    articleUrl: ({ db, col, id }) => `${akashaRoot}#/${enc(db)}/${enc(col)}/${enc(id)}`,
  };
}
