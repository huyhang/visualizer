// Editing a job's search plan before it runs: the box's own limits, checked here.

import type { Query } from "../api/types";

export const MAX_QUERIES = 6;
export const MAX_QUERY = 200;

/** The queries as they will be sent: trimmed, blanks dropped. */
export function cleanQueries(queries: Query[]): Query[] {
  return queries.map((q) => ({ ...q, q: q.q.trim() })).filter((q) => q.q);
}

/** Why the plan cannot be approved yet, or null. A refinement may search for nothing new. */
export function planProblem(queries: Query[], refining: boolean): string | null {
  const clean = cleanQueries(queries);
  if (clean.length > MAX_QUERIES) return `At most ${MAX_QUERIES} searches.`;
  if (!clean.length && !refining) return "Keep at least one search.";
  if (clean.some((q) => q.q.length > MAX_QUERY))
    return `Keep each search under ${MAX_QUERY} characters.`;
  return null;
}
