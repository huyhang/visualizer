// The scene form's references: the place, cast and items a scene names. They
// are Akasha articles -- Chronos never invents one -- so each is chosen from a
// search of the real canon. Ported from the classic sceneform.js.

import type { EntityRef } from "../../api/types";

export type RefRole = "location" | "characters" | "items";

/** The conventional collection each field draws from. */
export const ROLE_COLLECTION: Record<RefRole, string> = {
  location: "locations",
  characters: "characters",
  items: "items",
};

/**
 * Which collections a field may search. A book may name its collections
 * anything, so a field can also search the unconventional ones it observes --
 * but never another field's, or the Place picker would file a character as
 * the location.
 */
export function collectionOptions(observed: string[], role: RefRole): string[] {
  const mine = ROLE_COLLECTION[role];
  const others = Object.entries(ROLE_COLLECTION)
    .filter(([r]) => r !== role)
    .map(([, c]) => c);
  return Array.from(new Set([mine, ...observed.filter((c) => !others.includes(c))]));
}

const same = (a: EntityRef, b: EntityRef) =>
  a.id === b.id && a.collection === b.collection && a.database === b.database;

/** The choice after picking `ref`: one place replaces, a cast member joins (once). */
export function pick(chosen: EntityRef[], ref: EntityRef, multiple: boolean): EntityRef[] {
  if (!multiple) return [ref];
  return chosen.some((c) => same(c, ref)) ? chosen : [...chosen, ref];
}

export function unpick(chosen: EntityRef[], ref: EntityRef): EntityRef[] {
  return chosen.filter((c) => !same(c, ref));
}

/** Only the three fields a reference is made of: a picked search result carries a title too. */
export const bareRef = ({ database, collection, id }: EntityRef): EntityRef => ({
  database,
  collection,
  id,
});
