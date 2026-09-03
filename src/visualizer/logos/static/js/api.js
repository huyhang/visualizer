// The Logos API as the reader uses it: four reads and nothing else.
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

async function get(path) {
  const response = await fetch(BASE + path, {
    headers: { Accept: "application/json" },
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

const volumePath = (book, volume) =>
  `/books/${enc(book)}/volumes/${enc(volume)}`;

export const api = {
  books: () => get("/books"),
  manuscript: (book) => get(`/books/${enc(book)}`),
  volume: (book, volume) => get(`${volumePath(book, volume)}/manuscript`),
  // Full View only. Focused never reaches this, which is what makes "no
  // entities from any other service" a property of the network trace.
  scenes: (book, volume) => get(`${volumePath(book, volume)}/ui/scenes`),
};
