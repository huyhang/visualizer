// A wikilink target, resolved against the world the studio is in.

import type { ArticleRef } from "../api/types";

/** "db/col/id" | "col/id" -> where it points; a bare "id" names nothing here. */
export function resolveTarget(target: string, world: string): ArticleRef | null {
  const parts = target
    .split("|")[0]!
    .split("/")
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length >= 3)
    return { db: parts[0]!, col: parts[1]!, id: parts.slice(2).join("/") };
  if (parts.length === 2) return { db: world, col: parts[0]!, id: parts[1]! };
  return null;
}
