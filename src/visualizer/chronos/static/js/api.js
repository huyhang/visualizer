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

const calPath = (o, c) => `/calendars/${enc(o)}/${enc(c)}`;

function pageQuery({ filter, page, perPage, calendar } = {}) {
  const p = new URLSearchParams();
  if (filter) p.set("filter", filter);
  if (page) p.set("page", page);
  if (perPage) p.set("per_page", perPage);
  if (calendar) p.set("calendar", calendar);
  const q = p.toString();
  return q ? "?" + q : "";
}

// Which of a book's calendars to read ticks through. Omitted means its primary
// one. Every read that formats a tick takes it, and the server refuses a name
// the book has not attached rather than falling back — so a stale choice
// surfaces as an error instead of a page of quietly wrong dates.
function viewQuery(calendar, extra = "") {
  const q = calendar ? `calendar=${enc(calendar)}` : "";
  const joined = [extra, q].filter(Boolean).join("&");
  return joined ? "?" + joined : "";
}

export const api = {
  me: () => request("GET", "/auth/me"),

  listBooks: () => request("GET", "/books"),
  getBook: (book) => request("GET", bookPath(book)),
  // Whoever creates a book owns it outright — the server grants that, so there
  // is nothing to set up afterwards.
  createBook: (book, body) => request("POST", bookPath(book), { body }),
  // A *full replace*, not a patch: whatever the body omits is erased. Callers
  // must resend title, overview, calendar and terminus together (see bookform.js).
  updateBook: (book, body, rev) => request("PUT", bookPath(book), { body, ifMatch: rev }),

  // Deletes the book *and everything in it* — every plotline, every scene — and
  // sweeps the grants that named it, so the id is free again. Hard, with no
  // history behind it: there is nothing to undo it with, which is why the caller
  // confirms with the real counts first. Send the rev you loaded: the server
  // checks it before the cascade starts, so a refusal costs nothing.
  deleteBook: (book, rev) => request("DELETE", bookPath(book), { ifMatch: rev }),

  // Designate the one event every plotline in the book must end at. A book-level
  // write, so it lands immediately rather than waiting on a plotline's Save.
  setTerminus: (book, event) => request("POST", `${bookPath(book)}/terminus/${enc(event)}`),

  // Read helper: the paginated, filtered, name-ordered plotline table.
  listPlotlines: (book, opts) => request("GET", `${bookPath(book)}/ui/plotlines${pageQuery(opts)}`),

  // Everything wrong across every thread in the book, grouped by kind. The
  // reader's shape of `/books/{book}/validate`, in the same words the plotline
  // view uses — two of the messages quote ticks, hence the calendar.
  bookIssues: (book, { calendar } = {}) =>
    request("GET", `${bookPath(book)}/ui/issues${viewQuery(calendar)}`),

  // The book's scenes in story order — what the editor picks from.
  listEvents: (book, opts) => request("GET", `${bookPath(book)}/events${pageQuery(opts)}`),

  getPlotline: (book, id, { expand, calendar } = {}) =>
    request("GET", plPath(book, id) + viewQuery(calendar, expand ? "expand=events" : "")),

  createPlotline: (book, id, body) => request("POST", plPath(book, id), { body }),
  updatePlotline: (book, id, body, rev) => request("PUT", plPath(book, id), { body, ifMatch: rev }),
  // `inline` absorbs this thread into the ones that continue into it, so their
  // stories survive the deletion (the API refuses to orphan them otherwise).
  deletePlotline: (book, id, rev, { inline } = {}) =>
    request("DELETE", plPath(book, id) + (inline ? "?inline=true" : ""), { ifMatch: rev }),

  // What this candidate ordering would look like if saved. Writes nothing, and
  // works before the plotline exists — the editor's live conflict feedback.
  previewPlotline: (book, candidate, { calendar } = {}) =>
    request("POST", `${bookPath(book)}/ui/plotline-preview${viewQuery(calendar)}`,
      { body: candidate }),

  getEvent: (book, id, { calendar } = {}) =>
    request("GET", evPath(book, id) + viewQuery(calendar)),
  // `calendar` says which reckoning a `start_date`/`end_date` in the body is
  // written in — the same selector the reads take. It is not optional dressing:
  // the scene form shows the writer what their date resolves to *through that
  // calendar*, so a save that omitted it would store a different tick than the
  // one on screen. Bodies carrying plain ticks are unaffected either way.
  createEvent: (book, id, body, { calendar } = {}) =>
    request("POST", evPath(book, id) + viewQuery(calendar), { body }),
  updateEvent: (book, id, body, rev, { calendar } = {}) =>
    request("PUT", evPath(book, id) + viewQuery(calendar), { body, ifMatch: rev }),
  // `detach` first removes the scene from every plotline that lists it; without
  // it the API refuses with EVENT_IN_USE and names them, which is what the
  // caller shows before asking again. The book's terminus is refused either way
  // (TERMINUS_IN_USE) — designate a new ending first.
  deleteEvent: (book, id, rev, { detach } = {}) =>
    request("DELETE", evPath(book, id) + (detach ? "?detach=true" : ""), { ifMatch: rev }),

  // The whole book's story graph: nodes (with timing + role flags), plotline
  // lanes, and precedence edges tagged by plotline. Drives the connected-plots
  // view (and, later, the full story map).
  getGraph: (book, { calendar } = {}) =>
    request("GET", `${bookPath(book)}/graph${viewQuery(calendar)}`),

  // Read helper: a referenced Akasha article, proxied same-origin.
  getEntity: (book, database, collection, id) =>
    request("GET", `${bookPath(book)}/ui/entity/${enc(database)}/${enc(collection)}/${enc(id)}`),

  // What the book's calendar calls these ticks — as prose (`label`, `parts`)
  // and as numbers (`components`, what a date field puts back in its inputs).
  // Every reading comes back, not just the chosen one: `readings` dates the
  // tick in each calendar the book keeps, which is what the scene form shows.
  formatTicks: (book, ticks, { calendar } = {}) => {
    const p = new URLSearchParams();
    for (const t of ticks) p.append("tick", t);
    if (calendar) p.set("calendar", calendar);
    return request("GET", `${bookPath(book)}/ui/ticks?${p.toString()}`);
  },

  // The inverse: which ticks a pair of dates names. A POST for a read (a date
  // is a nested object; two of them say badly in a query string), and the one
  // reason the browser needs no mixed-radix arithmetic of its own — client and
  // server cannot disagree about what "Day 12" means if only one of them knows.
  // Takes exactly what a scene body takes, so what it accepts the save accepts.
  resolveDates: (book, timeframe, { calendar } = {}) =>
    request("POST", `${bookPath(book)}/ui/dates${viewQuery(calendar)}`, { body: timeframe }),

  // -- the calendar library --------------------------------------------------
  //
  // A calendar's identity is (owner, id): names like "imperial" are generic
  // enough that two writers will pick the same one, so neither a global
  // namespace nor a shared record would do. Attaching a calendar to a book
  // *copies* its descriptor — these calls are for browsing and managing the
  // library, never for reading a book's dates.

  listCalendars: () => request("GET", "/calendars"),
  getCalendar: (owner, id) => request("GET", calPath(owner, id)),
  // You may only create in your own library; the server refuses otherwise.
  createCalendar: (owner, id, body) => request("POST", calPath(owner, id), { body }),
  updateCalendar: (owner, id, body, rev) =>
    request("PUT", calPath(owner, id), { body, ifMatch: rev }),
  // Books that copied this calendar keep working — the copy *is* their
  // calendar. Only the provenance pointer goes dangling.
  deleteCalendar: (owner, id, rev) => request("DELETE", calPath(owner, id), { ifMatch: rev }),

  shareCalendar: (owner, id, username, role = "reader") =>
    request("PUT", `${calPath(owner, id)}/collaborators/${enc(username)}`, { body: { role } }),
  unshareCalendar: (owner, id, username) =>
    request("DELETE", `${calPath(owner, id)}/collaborators/${enc(username)}`),

  // The Akasha worlds this writer may draw a cast from, each with its
  // categories. Not book-scoped — the world is chosen while the book is being
  // created, so there is no book to scope to yet.
  listWorlds: () => request("GET", "/ui/worlds"),

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
