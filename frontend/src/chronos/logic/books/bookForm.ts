// The book form as pure functions: the draft it edits, what a save sends,
// what stops it, and what deleting would take with it.
//
// PUT replaces the whole book document, so an edit resends every stored field
// -- not just the ones on screen. Dropping `terminus` would silently
// un-designate the book's ending; dropping `overview` would delete prose with
// nothing on screen to say it went.

import type { Book, BookWrite, CalendarAttachment } from "../../api/types";
import { followTitle } from "../ids";

export interface BookDraft {
  title: string;
  id: string;
  idTouched: boolean;
  overview: string;
  world: string;
  terminus: string | null;
}

export function bookDraft(
  book: Book | null,
  worlds: { database: string }[] = [],
): BookDraft {
  if (book) {
    return {
      title: book.title ?? "",
      id: book.id,
      idTouched: true,
      overview: book.overview ?? "",
      world: book.world ?? "",
      terminus: book.terminus ?? null,
    };
  }
  // One world is the common case (one story, one canon): take it rather than
  // making the writer confirm the only option.
  return {
    title: "",
    id: "",
    idTouched: false,
    overview: "",
    world: worlds.length === 1 ? (worlds[0]?.database ?? "") : "",
    terminus: null,
  };
}

/** The draft after the title changed: the id follows until the writer takes it over. */
export function retitle(draft: BookDraft, title: string): BookDraft {
  return { ...draft, title, id: followTitle(title, draft.id, draft.idTouched) };
}

/**
 * Everything the book stores, as the API takes it. The `calendars` list,
 * never the older single `calendar`: the API refuses a body carrying both.
 * `null` is how "none" is said for the world and the ending.
 */
export function bookBody(
  draft: BookDraft,
  calendars: CalendarAttachment[],
  editing: boolean,
): BookWrite {
  const body: Record<string, unknown> = {
    title: draft.title.trim(),
    overview: draft.overview,
    calendars,
    world: draft.world || null,
  };
  if (editing) body.terminus = draft.terminus || null;
  return body as BookWrite;
}

export function bookProblems(draft: BookDraft): string[] {
  const out: string[] = [];
  if (!draft.title.trim()) out.push("Give the book a title.");
  if (!draft.id) out.push("Give the book an id.");
  return out;
}

export function bookFailure(
  code: string | null,
  status: number | null,
  id: string,
  fallback: string,
): string {
  if (code === "ALREADY_EXISTS")
    return `A book with the id “${id}” already exists. Choose another.`;
  if (status === 409)
    return "Someone else changed this book — reload the page before saving.";
  return fallback;
}

/** "3 plotlines and 17 scenes", minus whatever is zero, honest about a count it could not read. */
export function countPhrase(plotlines: number, scenes: number | null): string {
  const parts: string[] = [];
  if (plotlines) parts.push(`${plotlines} plotline${plotlines === 1 ? "" : "s"}`);
  if (scenes === null) parts.push("every scene in it");
  else if (scenes) parts.push(`${scenes} scene${scenes === 1 ? "" : "s"}`);
  return parts.join(" and ");
}

/**
 * Whether deleting needs the id typed. A book with nothing in it asks a plain
 * yes: a typing gate there would be theatre. A count we could not read is not
 * zero, so it gates.
 */
export function needsTypedConfirmation(plotlines: number, scenes: number | null): boolean {
  return plotlines > 0 || scenes !== 0;
}
