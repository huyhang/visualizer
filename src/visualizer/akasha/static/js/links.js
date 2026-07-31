// The [[wikilink]] convention: parsing tokens to targets, building the shortest
// unambiguous token for a target, and resolving/caching target titles.

import { api } from "./api.js";

// Parse a link token body ("db/col/id" | "col/id" | "id", optional "|label")
// relative to the article currently in scope. Returns {db, col, id, label}.
export function parseTarget(token, scope) {
  let label = null;
  const pipe = token.indexOf("|");
  if (pipe !== -1) { label = token.slice(pipe + 1).trim(); token = token.slice(0, pipe); }
  const parts = token.trim().split("/").map((p) => p.trim()).filter(Boolean);
  let db, col, id;
  if (parts.length >= 3) { [db, col, id] = parts; }
  else if (parts.length === 2) { db = scope.db; [col, id] = parts; }
  else { db = scope.db; col = scope.col; id = parts[0]; }
  return { db, col, id, label };
}

// The shortest token that unambiguously points at `target` from `scope`.
export function shortestToken(target, scope) {
  if (target.db === scope.db && target.col === scope.col) return target.id;
  if (target.db === scope.db) return `${target.col}/${target.id}`;
  return `${target.db}/${target.col}/${target.id}`;
}

export function targetKey(t) { return `${t.db}/${t.col}/${t.id}`; }

// Resolve a target's title (and existence), cached per page load.
const cache = new Map();
export function resolveTarget(target) {
  const key = targetKey(target);
  if (cache.has(key)) return cache.get(key);
  const promise = api.getDoc(target.db, target.col, target.id)
    .then((doc) => ({ exists: true, title: doc.document.title || target.id, rev: doc.rev }))
    .catch(() => ({ exists: false, title: target.id }));
  cache.set(key, promise);
  return promise;
}

export function invalidate(target) { cache.delete(targetKey(target)); }
