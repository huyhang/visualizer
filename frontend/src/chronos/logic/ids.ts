// Ids for new records. A new thread, scene or goal is created *at* an id, and
// the writer should not have to invent one: it follows the title until they
// type one of their own, and then it is theirs.

import { slugify } from "./text";

/** The id field's value after the title changed: derived, unless the writer took it over. */
export function followTitle(title: string, id: string, takenOver: boolean): string {
  return takenOver ? id : slugify(title);
}

/** Why `id` cannot be used, or null when it can. */
export function idProblem(id: string, taken: Iterable<string> = []): string | null {
  if (!id) return "Give it a name or an id.";
  if (id !== slugify(id)) return "Use lowercase letters, digits and hyphens.";
  for (const existing of taken)
    if (existing === id) return "That id is already taken in this book.";
  return null;
}
