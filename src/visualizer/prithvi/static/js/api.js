// The Prithvi API as the page uses it. Same origin, session cookie, and
// `If-Match` on every write that the API requires one for.
//
// `BASE` comes from the template's `request.script_root`, so the same bundle
// works at `/prithvi` behind the gateway and at `/` when prithvi runs alone --
// the reason nothing here hardcodes a prefix.

const enc = encodeURIComponent;
const BASE = (typeof window !== "undefined" && window.__BASE__) || "";
const SVG_TYPE = "image/svg+xml";

export class ApiError extends Error {
  constructor(status, body) {
    super((body && body.error) || `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }

  get code() {
    return (this.body && this.body.code) || null;
  }

  get isConflict() {
    return this.status === 409;
  }
}

async function readJson(response) {
  try {
    return await response.json();
  } catch (error) {
    // A body that is not JSON carries nothing we can show; the status still
    // does. Swallowed deliberately and only here, where there is genuinely
    // nothing else to learn -- never around a request that was meant to work.
    return null;
  }
}

async function request(method, path, { body, ifMatch, contentType } = {}) {
  const headers = { Accept: "application/json" };
  const options = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = contentType || "application/json";
    options.body = contentType ? body : JSON.stringify(body);
  }
  if (ifMatch !== undefined && ifMatch !== null) {
    headers["If-Match"] = String(ifMatch);
  }
  const response = await fetch(BASE + path, options);
  if (response.status === 204) return null;
  const payload = await readJson(response);
  if (!response.ok) throw new ApiError(response.status, payload);
  return payload;
}

async function requestSvg(path) {
  const response = await fetch(BASE + path, { headers: { Accept: SVG_TYPE } });
  if (!response.ok) throw new ApiError(response.status, await readJson(response));
  return response.text();
}

const mapsPath = (world) => `/worlds/${enc(world)}/maps`;
const mapPath = (world, map) => `${mapsPath(world)}/${enc(map)}`;
const pinPath = (world, map, article) =>
  `${mapPath(world, map)}/pins/${enc(article.collection)}/${enc(article.id)}`;

export const api = {
  worlds: () => request("GET", "/ui/worlds"),

  articles: (world, query) => request(
    "GET",
    `/ui/worlds/${enc(world)}/articles${query ? `?q=${enc(query)}` : ""}`,
  ),

  preview: (world, article) => request(
    "GET",
    `/ui/worlds/${enc(world)}/articles/${enc(article.collection)}/${enc(article.id)}`,
  ),

  maps: (world) => request("GET", `${mapsPath(world)}?per_page=100`),
  map: (world, map) => request("GET", mapPath(world, map)),
  svg: (world, map) => requestSvg(`${mapPath(world, map)}/svg`),

  // Creating a map does not take `If-Match`: there is no revision to be stale
  // against yet. Every other write below does.
  uploadMap: (world, map, file) => request("POST", mapPath(world, map), {
    body: file,
    contentType: SVG_TYPE,
  }),
  deleteMap: (world, map, rev) => request("DELETE", mapPath(world, map), {
    ifMatch: rev,
  }),

  pins: (world, map) => request("GET", `${mapPath(world, map)}/pins?per_page=100`),
  createPin: (world, map, article, position) => request(
    "POST", pinPath(world, map, article), { body: position },
  ),
  movePin: (world, map, pin) => request(
    "PUT", pinPath(world, map, pin.article), { body: pin.position, ifMatch: pin.rev },
  ),
  deletePin: (world, map, pin) => request(
    "DELETE", pinPath(world, map, pin.article), { ifMatch: pin.rev },
  ),
};
