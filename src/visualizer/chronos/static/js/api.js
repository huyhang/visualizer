// Thin wrapper over Chronos's JSON API. Every call carries the session cookie
// automatically (same-origin). Writes send If-Match so a save that would clobber
// someone else's edit is refused (409) rather than silently winning.
//
// No CSRF token is attached: Chronos's JSON routes are csrf-exempt by design (so
// scripts can drive the same API), and the session cookie is SameSite=Lax, which
// keeps a cross-site form from carrying it into a state-changing request.

const enc = encodeURIComponent;

// The path Chronos is mounted under: "" when served standalone, "/timeline"
// behind the single-origin gateway. Prepended to every request so the same JS
// works at either mount (set by the template from request.script_root).
export const BASE = (typeof window !== "undefined" && window.__BASE__) || "";

export class ApiError extends Error {
  constructor(status, body) {
    super((body && body.error) || `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
  get isConflict() { return this.status === 409; }
  get isForbidden() { return this.status === 403; }
  get isNotFound() { return this.status === 404; }
  // The machine-readable reason, e.g. "PLOTLINE_IN_USE" — what the UI branches on.
  get code() { return (this.body && this.body.code) || null; }
  get evidence() { return (this.body && this.body.evidence) || {}; }
}

async function request(method, url, { body, ifMatch } = {}) {
  const headers = { Accept: "application/json" };
  const opts = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (ifMatch !== undefined && ifMatch !== null) headers["If-Match"] = String(ifMatch);
  const resp = await fetch(BASE + url, opts);
  if (resp.status === 204) return null;
  let payload = null;
  try { payload = await resp.json(); } catch (e) { /* empty body */ }
  if (!resp.ok) throw new ApiError(resp.status, payload);
  return payload;
}

const bookPath = (b) => `/books/${enc(b)}`;
const plPath = (b, p) => `${bookPath(b)}/plotlines/${enc(p)}`;
const evPath = (b, e) => `${bookPath(b)}/events/${enc(e)}`;

function pageQuery({ filter, page, perPage } = {}) {
  const p = new URLSearchParams();
  if (filter) p.set("filter", filter);
  if (page) p.set("page", page);
  if (perPage) p.set("per_page", perPage);
  const q = p.toString();
  return q ? "?" + q : "";
}

export const api = {
  me: () => request("GET", "/auth/me"),

  listBooks: () => request("GET", "/books"),
  getBook: (book) => request("GET", bookPath(book)),

  // Read helper: the paginated, filtered, name-ordered plotline table.
  listPlotlines: (book, opts) => request("GET", `${bookPath(book)}/ui/plotlines${pageQuery(opts)}`),

  // The book's scenes in story order — what the editor picks from.
  listEvents: (book, opts) => request("GET", `${bookPath(book)}/events${pageQuery(opts)}`),

  getPlotline: (book, id, { expand } = {}) =>
    request("GET", `${plPath(book, id)}${expand ? "?expand=events" : ""}`),

  createPlotline: (book, id, body) => request("POST", plPath(book, id), { body }),
  updatePlotline: (book, id, body, rev) => request("PUT", plPath(book, id), { body, ifMatch: rev }),
  // `inline` absorbs this thread into the ones that continue into it, so their
  // stories survive the deletion (the API refuses to orphan them otherwise).
  deletePlotline: (book, id, rev, { inline } = {}) =>
    request("DELETE", plPath(book, id) + (inline ? "?inline=true" : ""), { ifMatch: rev }),

  // What this candidate ordering would look like if saved. Writes nothing, and
  // works before the plotline exists — the editor's live conflict feedback.
  previewPlotline: (book, candidate) =>
    request("POST", `${bookPath(book)}/ui/plotline-preview`, { body: candidate }),

  getEvent: (book, id) => request("GET", evPath(book, id)),
  createEvent: (book, id, body) => request("POST", evPath(book, id), { body }),
  updateEvent: (book, id, body, rev) => request("PUT", evPath(book, id), { body, ifMatch: rev }),

  // The whole book's story graph: nodes (with timing + role flags), plotline
  // lanes, and precedence edges tagged by plotline. Drives the connected-plots
  // view (and, later, the full story map).
  getGraph: (book) => request("GET", `${bookPath(book)}/graph`),

  // Read helper: a referenced Akasha article, proxied same-origin.
  getEntity: (book, database, collection, id) =>
    request("GET", `${bookPath(book)}/ui/entity/${enc(database)}/${enc(collection)}/${enc(id)}`),

  // What the book's calendar calls these ticks. One way only — a fantasy
  // calendar cannot be parsed back, so the browser never guesses a label.
  formatTicks: (book, ticks) => {
    const p = new URLSearchParams();
    for (const t of ticks) p.append("tick", t);
    return request("GET", `${bookPath(book)}/ui/ticks?${p.toString()}`);
  },

  // Type-ahead over the articles a scene could reference, same-origin and
  // already filtered to what this user may read.
  searchEntities: (book, { q, collection, database } = {}) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (collection) p.set("collection", collection);
    if (database) p.set("database", database);
    return request("GET", `${bookPath(book)}/ui/entities?${p.toString()}`);
  },
};
