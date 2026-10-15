import type { ArticleRef } from "../doc/types";

/** An Akasha ref written `database/collection/id`, or null if it is not one. */
export function parseRef(ref: string): ArticleRef | null {
  const parts = ref.split("/");
  if (parts.length !== 3 || parts.some((part) => !part.trim())) return null;
  const [database, collection, id] = parts as [string, string, string];
  return { database, collection, id };
}
