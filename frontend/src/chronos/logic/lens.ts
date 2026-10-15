// The character lens: pick someone (or somewhere, or something) and every
// screen lights up the scenes they are in and fades the rest.
//
// Who is in a scene comes with the book's scene listing, each row carrying its
// place, cast and things whole (`cast`): one read, shared with the Scenes
// screen, and every scene in it -- on a thread or not.

import type { EntityRef } from "../api/types";

export const refKey = (ref: EntityRef) => `${ref.database}/${ref.collection}/${ref.id}`;

/** Every scene in the listing, and who, where and what is in it. */
export function castIndex(
  scenes: { id: string; cast?: EntityRef[] }[],
): Map<string, EntityRef[]> {
  return new Map(scenes.map((s) => [s.id, s.cast ?? []]));
}

/** The scenes `ref` is in. */
export function scenesFeaturing(
  index: Map<string, EntityRef[]>,
  ref: EntityRef,
): Set<string> {
  const key = refKey(ref);
  const found = new Set<string>();
  for (const [scene, cast] of index)
    if (cast.some((r) => refKey(r) === key)) found.add(scene);
  return found;
}

export interface CastMember {
  ref: EntityRef;
  scenes: number;
}

/** Everyone who appears, most scenes first, so the main cast is at the top of the picker. */
export function castList(index: Map<string, EntityRef[]>): CastMember[] {
  const counts = new Map<string, CastMember>();
  for (const cast of index.values()) {
    for (const ref of new Map(cast.map((r) => [refKey(r), r])).values()) {
      const key = refKey(ref);
      const member = counts.get(key) ?? { ref, scenes: 0 };
      member.scenes += 1;
      counts.set(key, member);
    }
  }
  const order = (c: string) => ["characters", "locations", "items"].indexOf(c) + 1 || 9;
  return [...counts.values()].sort(
    (a, b) =>
      order(a.ref.collection) - order(b.ref.collection) ||
      b.scenes - a.scenes ||
      a.ref.id.localeCompare(b.ref.id),
  );
}
