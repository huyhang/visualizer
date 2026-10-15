// Stable block ids: what review anchors, reader notes and bookmarks point at.

export type IdFactory = () => string;

export const newBlockId: IdFactory = () => {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return `p-${globalThis.crypto.randomUUID()}`;
  }
  return `p-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
};

/**
 * The ids a sequence of blocks should carry: each keeps its own unless it is
 * missing or an earlier block already holds it, which is what splitting a
 * paragraph and pasting a copy both produce. The first holder keeps the id,
 * so the passage a note was anchored to stays anchored.
 */
export function uniqueIds(held: readonly (string | null | undefined)[], make: IdFactory) {
  const seen = new Set<string>();
  return held.map((id) => {
    const kept = id && id.trim() && !seen.has(id) ? id : make();
    seen.add(kept);
    return kept;
  });
}
