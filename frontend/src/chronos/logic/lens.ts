// The character lens: pick someone (or somewhere, or something) and every
// screen lights up the scenes they are in and fades the rest.
//
// Who is in a scene is on each scene, and the threads already carry their
// scenes in full (`?expand=events`), so the cast is read from the threads --
// one request per thread, shared with the screens that show them.

import type { EntityRef, EventSummary, Plotline } from "../api/types";

export const refKey = (ref: EntityRef) => `${ref.database}/${ref.collection}/${ref.id}`;

/** Every scene the threads pass through, and who, where and what is in it. */
export function castIndex(plotlines: Plotline[]): Map<string, EntityRef[]> {
  const index = new Map<string, EntityRef[]>();
  for (const plotline of plotlines) {
    for (const entry of plotline.effective_events) {
      if (typeof entry === "string" || index.has(entry.id)) continue;
      index.set(entry.id, sceneCast(entry));
    }
  }
  return index;
}

export function sceneCast(
  scene: Pick<EventSummary, "characters" | "items" | "location">,
): EntityRef[] {
  return [
    ...(scene.characters ?? []),
    ...(scene.location ? [scene.location] : []),
    ...(scene.items ?? []),
  ];
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
