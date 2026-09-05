// The Logos API as the reader uses it. Manuscript prose remains read-only;
// writes below affect only the current account's reader layer or publication
// settings a writer is allowed to change.
//
// There is no write here and no `If-Match`, because there is nothing this page
// can change. `BASE` comes from the template's `request.script_root`, so one
// bundle works at `/logos` behind the gateway and at `/` when Logos runs on
// its own port -- the same reason nothing below hardcodes a prefix.

const enc = encodeURIComponent;

export const BASE = (typeof window !== "undefined" && window.__BASE__) || "";

export class ApiError extends Error {
  constructor(status, body) {
    super((body && body.error) || `HTTP ${status}`);
    this.status = status;
    this.code = (body && body.code) || null;
  }
}

async function request(path, options = {}) {
  const response = await fetch(BASE + path, {
    ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  let body = null;
  try {
    body = await response.json();
  } catch (_error) {
    // A non-JSON body carries nothing we could show; the status still does.
  }
  if (!response.ok) throw new ApiError(response.status, body);
  return body;
}

async function download(path) {
  const response = await fetch(BASE + path, { headers: { Accept: "application/octet-stream" } });
  if (!response.ok) {
    let body = null;
    try { body = await response.json(); } catch (_error) { /* status is enough */ }
    throw new ApiError(response.status, body);
  }
  // 202 means the file is not ready yet, which is a state and not a download.
  if (response.status === 202) return null;
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  return { blob: await response.blob(), filename: match ? match[1] : "manuscript" };
}

const get = (path) => request(path);
const json = (method, path, body, revision = null, options = {}) => request(path, {
  ...options,
  method,
  headers: {
    "Content-Type": "application/json",
    ...(revision === null ? {} : { "If-Match": `"${revision}"` }),
  },
  body: body === undefined ? undefined : JSON.stringify(body),
});

const volumePath = (book, volume) =>
  `/books/${enc(book)}/volumes/${enc(volume)}`;

export const api = {
  books: () => get("/books"),
  manuscript: (book) => get(`/books/${enc(book)}`),
  section: (book, volume, section) =>
    get(`${volumePath(book, volume)}/sections/${enc(section)}`),
  // Full View only. Focused never reaches this, which is what makes "no
  // entities from any other service" a property of the network trace.
  scenes: (book, volume, section) =>
    get(`${volumePath(book, volume)}/sections/${enc(section)}/ui/scenes`),
  search: (book, query, offset = 0) => get(
    `/books/${enc(book)}/search?${new URLSearchParams({ q: query, offset })}`,
  ),
  readerSettings: () => get("/me/reader-settings"),
  saveReaderSettings: (settings) => json("PUT", "/me/reader-settings", settings),
  readerItems: (book) => get(`/books/${enc(book)}/me/items`),
  createReaderItem: (book, item) => json("POST", `/books/${enc(book)}/me/items`, item),
  updateReaderItem: (book, item, patch, revision) => json(
    "PUT", `/books/${enc(book)}/me/items/${enc(item)}`, patch, revision,
  ),
  deleteReaderItem: (book, item, revision) => json(
    "DELETE", `/books/${enc(book)}/me/items/${enc(item)}`, undefined, revision,
  ),
  readingPosition: (book) => get(`/books/${enc(book)}/me/position`),
  saveReadingPosition: (book, position) => json(
    "PUT", `/books/${enc(book)}/me/position`, position, null, { keepalive: true },
  ),
  publication: (book) => get(`/books/${enc(book)}/publication`),
  createPublication: (book, metadata) => json(
    "POST", `/books/${enc(book)}/publication`, metadata,
  ),
  updatePublication: (book, metadata, revision) => json(
    "PUT", `/books/${enc(book)}/publication`, metadata, revision,
  ),
  saveCover: (book, bytes) => request(`/books/${enc(book)}/publication/cover`, {
    method: "PUT", body: bytes,
  }),
  deleteCover: (book) => request(`/books/${enc(book)}/publication/cover`, {
    method: "DELETE",
  }),
  exportEpub: (book) => download(`/books/${enc(book)}/exports/epub`),
  // The PDF is started, then polled: a whole series takes minutes to lay out,
  // which is longer than a proxy will hold a request open.
  startPdf: (book) => json("POST", `/books/${enc(book)}/exports/pdf`),
  collectPdf: (book, job) => download(
    `/books/${enc(book)}/exports/pdf/${enc(job)}`,
  ),
};
