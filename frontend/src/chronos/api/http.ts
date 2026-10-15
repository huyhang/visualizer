// `ChronosApi` over Chronos's JSON routes, with the session cookie the page
// already holds. No CSRF token: the JSON routes are csrf-exempt by design and
// the cookie is SameSite=Lax. `fetch` is injected so request building is testable.

import type { ChronosApi, EntityQuery, PageOptions, ViewOptions } from "./ChronosApi";
import { ChronosApiError } from "./errors";
import type { Book, Goal, LibraryCalendar, TickLabel, World } from "./types";

export interface HttpApiOptions {
  /** Where Chronos is mounted: "" when it owns the origin, "/timeline" behind the gateway. */
  base: string;
  fetch?: typeof fetch;
}

interface CallOptions {
  body?: unknown;
  rev?: number;
}

const enc = encodeURIComponent;

/** `?a=1&b=2` from the entries that have a value, or "" when none do. */
export function queryString(
  params: [string, string | number | null | undefined][],
): string {
  const query = new URLSearchParams();
  for (const [key, value] of params) {
    if (value !== undefined && value !== null && value !== "")
      query.append(key, String(value));
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

const view = (options: ViewOptions = {}, extra: [string, string | null][] = []) =>
  queryString([...extra, ["calendar", options.calendar]]);

const paging = ({ filter, page, perPage, calendar }: PageOptions = {}) =>
  queryString([
    ["filter", filter],
    ["page", page],
    ["per_page", perPage],
    ["calendar", calendar],
  ]);

/** The refusal Chronos sent, as an error the page can branch on. */
export function apiError(status: number, payload: unknown): ChronosApiError {
  const body = (payload && typeof payload === "object" ? payload : {}) as Record<
    string,
    unknown
  >;
  return new ChronosApiError(
    status,
    typeof body.error === "string" ? body.error : `The server answered ${status}.`,
    typeof body.code === "string" ? body.code : null,
    body.evidence && typeof body.evidence === "object"
      ? (body.evidence as Record<string, unknown>)
      : {},
  );
}

export function createHttpApi(options: HttpApiOptions): ChronosApi {
  const { base } = options;
  const send = options.fetch ?? window.fetch.bind(window);

  async function call<T>(method: string, path: string, { body, rev }: CallOptions = {}) {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (rev !== undefined) headers["If-Match"] = String(rev);
    const response = await send(base + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 204) return undefined as T;
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw apiError(response.status, payload);
    return payload as T;
  }

  const book = (b: string) => `/books/${enc(b)}`;
  const plotline = (b: string, p: string) => `${book(b)}/plotlines/${enc(p)}`;
  const event = (b: string, e: string) => `${book(b)}/events/${enc(e)}`;
  const goal = (b: string, g: string) => `${book(b)}/goals/${enc(g)}`;
  const calendar = (o: string, c: string) => `/calendars/${enc(o)}/${enc(c)}`;
  const flag = (name: string, on?: boolean) => (on ? `?${name}=true` : "");

  return {
    me: () => call("GET", "/auth/me"),

    listBooks: async () => (await call<{ books: Book[] }>("GET", "/books")).books,
    getBook: (b) => call("GET", book(b)),
    createBook: (b, body) => call("POST", book(b), { body }),
    updateBook: (b, body, rev) => call("PUT", book(b), { body, rev }),
    deleteBook: (b, rev) => call("DELETE", book(b), { rev }),
    setTerminus: (b, e) => call("POST", `${book(b)}/terminus/${enc(e)}`),

    listPlotlines: (b, opts) => call("GET", `${book(b)}/ui/plotlines${paging(opts)}`),
    getPlotline: (b, p, opts) =>
      call("GET", plotline(b, p) + view(opts, [["expand", "events"]])),
    createPlotline: (b, p, body) => call("POST", plotline(b, p), { body }),
    updatePlotline: (b, p, body, rev) => call("PUT", plotline(b, p), { body, rev }),
    deletePlotline: (b, p, rev, inline) =>
      call("DELETE", plotline(b, p) + flag("inline", inline), { rev }),
    previewPlotline: (b, candidate, opts) =>
      call("POST", `${book(b)}/ui/plotline-preview${view(opts)}`, { body: candidate }),

    bookIssues: (b, opts) => call("GET", `${book(b)}/ui/issues${view(opts)}`),

    listEvents: (b, opts) => call("GET", `${book(b)}/events${paging(opts)}`),
    timelineEvents: (b, opts) => call("GET", `${book(b)}/ui/timeline${paging(opts)}`),
    getEvent: (b, e, opts) => call("GET", event(b, e) + view(opts)),
    createEvent: (b, e, body, opts) => call("POST", event(b, e) + view(opts), { body }),
    updateEvent: (b, e, body, rev, opts) =>
      call("PUT", event(b, e) + view(opts), { body, rev }),
    deleteEvent: (b, e, rev, detach) =>
      call("DELETE", event(b, e) + flag("detach", detach), { rev }),

    listGoals: async (b, opts) =>
      (await call<{ goals: Goal[] }>("GET", `${book(b)}/goals${view(opts)}`)).goals,
    getGoal: (b, g, opts) => call("GET", goal(b, g) + view(opts)),
    createGoal: (b, g, body) => call("POST", goal(b, g), { body }),
    updateGoal: (b, g, body, rev) => call("PUT", goal(b, g), { body, rev }),
    deleteGoal: (b, g, rev, detach) =>
      call("DELETE", goal(b, g) + flag("detach", detach), { rev }),

    getGraph: (b, opts) => call("GET", `${book(b)}/graph${view(opts)}`),

    getEntity: (b, database, collection, id) =>
      call("GET", `${book(b)}/ui/entity/${enc(database)}/${enc(collection)}/${enc(id)}`),
    searchEntities: (b, { q, collection, database }: EntityQuery) =>
      call(
        "GET",
        `${book(b)}/ui/entities${queryString([
          ["q", q],
          ["collection", collection],
          ["database", database],
        ])}`,
      ),
    listWorlds: async () =>
      (await call<{ worlds?: World[] }>("GET", "/ui/worlds")).worlds ?? [],

    formatTicks: async (b, ticks, opts) => {
      const query = queryString([
        ...ticks.map((t): [string, number] => ["tick", t]),
        ["calendar", opts?.calendar],
      ]);
      return (await call<{ ticks: TickLabel[] }>("GET", `${book(b)}/ui/ticks${query}`))
        .ticks;
    },
    resolveDates: (b, timeframe, opts) =>
      call("POST", `${book(b)}/ui/dates${view(opts)}`, { body: timeframe }),

    listCalendars: async () =>
      (await call<{ calendars: LibraryCalendar[] }>("GET", "/calendars")).calendars,
    createCalendar: (o, c, body) => call("POST", calendar(o, c), { body }),
    updateCalendar: (o, c, body, rev) => call("PUT", calendar(o, c), { body, rev }),
    deleteCalendar: (o, c, rev) => call("DELETE", calendar(o, c), { rev }),
    shareCalendar: (o, c, username, role = "reader") =>
      call("PUT", `${calendar(o, c)}/collaborators/${enc(username)}`, { body: { role } }),
    unshareCalendar: (o, c, username) =>
      call("DELETE", `${calendar(o, c)}/collaborators/${enc(username)}`),
  };
}
