// Thin wrapper over the JSON document API. Every call carries the session
// cookie automatically; writes send If-Match for optimistic concurrency.

const enc = encodeURIComponent;

export class ApiError extends Error {
  constructor(status, body) {
    super((body && body.error) || `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
  get isConflict() { return this.status === 409; }
  get isForbidden() { return this.status === 403; }
  get isNotFound() { return this.status === 404; }
}

async function request(method, url, { body, ifMatch } = {}) {
  const headers = { Accept: "application/json" };
  const opts = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (ifMatch !== undefined && ifMatch !== null) headers["If-Match"] = String(ifMatch);
  const resp = await fetch(url, opts);
  if (resp.status === 204) return null;
  let payload = null;
  try { payload = await resp.json(); } catch (e) { /* empty body */ }
  if (!resp.ok) throw new ApiError(resp.status, payload);
  return payload;
}

const colPath = (db, col) => `/databases/${enc(db)}/collections/${enc(col)}`;
const docPath = (db, col, id) => `${colPath(db, col)}/documents/${enc(id)}`;

export const api = {
  me: () => request("GET", "/auth/me"),

  listDatabases: () => request("GET", "/databases"),
  listCollections: (db) => request("GET", `/databases/${enc(db)}/collections`),
  createCollection: (db, col) =>
    request("POST", `/databases/${enc(db)}/collections/${enc(col)}`),
  // Only ever succeeds when no live document is left; the server drops the
  // database too when this was its last collection. `purge` additionally
  // discards the version history of documents deleted from it, which is the
  // only way a collection that has ever held something can go.
  deleteCollection: (db, col, { purge } = {}) =>
    request("DELETE", colPath(db, col) + (purge ? "?purge=1" : "")),
  deleteDatabase: (db) => request("DELETE", `/databases/${enc(db)}`),

  // One page of a collection. `filter` searches the whole article by default;
  // `match: "name"` narrows it to the title and slug, which is what the sidebar
  // wants — it cannot show why a body match matched.
  listDocuments: (db, col, { filter, page, perPage, match } = {}) => {
    const p = new URLSearchParams();
    if (filter) p.set("filter", filter);
    if (page) p.set("page", page);
    if (perPage) p.set("per_page", perPage);
    if (match) p.set("match", match);
    const q = p.toString();
    return request("GET", `${colPath(db, col)}/documents${q ? "?" + q : ""}`);
  },
  recent: (limit) => request("GET", `/recent${limit ? `?limit=${limit}` : ""}`),

  // Articles deleted from a collection, each with the revision a restore would
  // bring back (null when history has been pruned down to deletions alone).
  listDeleted: (db, col) => request("GET", colPath(db, col) + "/deleted"),

  // Field-aware search within one collection: `key` finds articles that *have*
  // a field, `text` finds articles that mention something.
  search: (db, col, { key, text } = {}) => {
    const p = new URLSearchParams();
    if (key) p.set("key", key);
    if (text) p.set("text", text);
    return request("GET", `${colPath(db, col)}/search?${p.toString()}`);
  },

  getDoc: (db, col, id) => request("GET", docPath(db, col, id)),
  createDoc: (db, col, id, document) => request("POST", docPath(db, col, id), { body: document }),
  updateDoc: (db, col, id, document, rev) =>
    request("PUT", docPath(db, col, id), { body: document, ifMatch: rev }),
  deleteDoc: (db, col, id, rev) => request("DELETE", docPath(db, col, id), { ifMatch: rev }),

  listVersions: (db, col, id) => request("GET", docPath(db, col, id) + "/versions"),
  getVersion: (db, col, id, rev) => request("GET", docPath(db, col, id) + `/versions/${rev}`),
  diff: (db, col, id, from, to) =>
    request("GET", docPath(db, col, id) + `/diff?from=${from}&to=${to}`),
  restore: (db, col, id, rev) => request("POST", docPath(db, col, id) + `/restore/${rev}`),

  suggest: (q, db, col) => {
    const p = new URLSearchParams({ q });
    if (db) p.set("db", db);
    if (col) p.set("col", col);
    return request("GET", `/suggest?${p.toString()}`);
  },

  // Your saved collaborator roster (drives the sharing pickers).
  contacts: () => request("GET", "/account/contacts"),

  // Sharing: manage who can access a collection or a single document. The
  // server includes the owner in the list — filter yourself out client-side.
  listCollaborators: (db, col, id) =>
    request("GET", (id ? docPath(db, col, id) : colPath(db, col)) + "/collaborators"),
  setCollaborator: (db, col, id, username, role) =>
    request("PUT", (id ? docPath(db, col, id) : colPath(db, col)) + `/collaborators/${enc(username)}`, { body: { role } }),
  removeCollaborator: (db, col, id, username) =>
    request("DELETE", (id ? docPath(db, col, id) : colPath(db, col)) + `/collaborators/${enc(username)}`),
};
