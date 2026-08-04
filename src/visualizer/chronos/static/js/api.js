// Thin wrapper over Chronos's JSON API. Every call carries the session cookie
// automatically (same-origin); this UI is read-only, so there are no writes.

const enc = encodeURIComponent;

export class ApiError extends Error {
  constructor(status, body) {
    super((body && body.error) || `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
  get isForbidden() { return this.status === 403; }
  get isNotFound() { return this.status === 404; }
}

async function request(method, url) {
  const resp = await fetch(url, { method, headers: { Accept: "application/json" } });
  if (resp.status === 204) return null;
  let payload = null;
  try { payload = await resp.json(); } catch (e) { /* empty body */ }
  if (!resp.ok) throw new ApiError(resp.status, payload);
  return payload;
}

const bookPath = (b) => `/books/${enc(b)}`;

export const api = {
  me: () => request("GET", "/auth/me"),

  listBooks: () => request("GET", "/books"),
  getBook: (book) => request("GET", bookPath(book)),

  // Read helper: the paginated, filtered, name-ordered plotline table.
  listPlotlines: (book, { filter, page, perPage } = {}) => {
    const p = new URLSearchParams();
    if (filter) p.set("filter", filter);
    if (page) p.set("page", page);
    if (perPage) p.set("per_page", perPage);
    const q = p.toString();
    return request("GET", `${bookPath(book)}/ui/plotlines${q ? "?" + q : ""}`);
  },

  getPlotline: (book, id, { expand } = {}) =>
    request("GET", `${bookPath(book)}/plotlines/${enc(id)}${expand ? "?expand=events" : ""}`),

  getEvent: (book, id) => request("GET", `${bookPath(book)}/events/${enc(id)}`),

  // Read helper: a referenced Akasha article, proxied same-origin.
  getEntity: (book, database, collection, id) =>
    request("GET", `${bookPath(book)}/ui/entity/${enc(database)}/${enc(collection)}/${enc(id)}`),
};
