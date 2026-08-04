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
  listDocuments: (db, col, { limit, after } = {}) => {
    const p = new URLSearchParams();
    if (limit) p.set("limit", limit);
    if (after) p.set("after", after);
    const q = p.toString();
    return request("GET", `/databases/${enc(db)}/collections/${enc(col)}/documents${q ? "?" + q : ""}`);
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
