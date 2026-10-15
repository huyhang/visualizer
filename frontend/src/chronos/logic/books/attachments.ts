// The book form's calendars, as pure functions over the rows a writer edits.
// Ported from the classic page's calendarlist.js and calendarfield.js.
//
// An attachment *names* a library calendar and says how this book uses it --
// the label it goes by, the span of ticks its culture kept it, and for an
// Earth calendar which moment this book's tick 0 was. It never carries the
// calendar itself: the server copies the descriptor out of the library, so
// there is no second copy in the browser to fall out of step. "No calendar"
// is no rows at all; the first row is the book's primary reckoning.

import type {
  CalendarAttachment,
  CalendarDescriptor,
  CalendarSource,
  LibraryCalendar,
} from "../../api/types";
import { dateUnits, dateValue, emptyDate, dateDraft, type DateDraft } from "../calendars";
import { slugify } from "../text";

/** The server's cap: stated here to hide the Add button, refused there either way. */
export const MAX_CALENDARS = 8;
const DEFAULT_ID = "default";

export interface AttachmentDraft {
  /** Stable across reorders, for React; never sent. */
  key: string;
  label: string;
  id: string;
  /** Whether the writer typed the id; otherwise it follows the label. */
  idTouched: boolean;
  /** The library calendar this row names, or null until one is chosen. */
  source: { owner: string; calendar: string } | null;
  /** What the book already holds (owner, calendar, rev), so a plain save keeps it. */
  held: CalendarSource | null;
  /** Set only by accepting the update offer: the one way a library change reaches a book. */
  tookUpdate: boolean;
  /** The descriptor this book holds for the row -- not the library's, which may have moved on. */
  heldDescriptor: CalendarDescriptor | null;
  from: string;
  until: string;
  /** Where this book's tick 0 falls on Earth's timeline, for a Gregorian calendar. */
  origin: DateDraft;
  offset: string;
}

let keys = 0;
const nextKey = () => `row-${++keys}`;

export function blankAttachment(): AttachmentDraft {
  return {
    key: nextKey(),
    label: "",
    id: "",
    idTouched: false,
    source: null,
    held: null,
    tookUpdate: false,
    heldDescriptor: null,
    from: "",
    until: "",
    origin: emptyDate(),
    offset: "Z",
  };
}

/** The rows for a book as loaded: primary first, as the server lists them. */
export function draftsFrom(calendars: CalendarAttachment[] = []): AttachmentDraft[] {
  const ordered = [...calendars].sort(
    (a, b) => Number(Boolean(b.primary)) - Number(Boolean(a.primary)),
  );
  return ordered.map((a) => {
    const held = a.source ?? null;
    const origin = splitOrigin(a.origin ?? null);
    return {
      ...blankAttachment(),
      label: a.label ?? "",
      id: a.id,
      idTouched: Boolean(a.id) && a.id !== slugify(a.label ?? ""),
      source: held ? { owner: held.owner, calendar: held.calendar } : null,
      held,
      heldDescriptor: a.descriptor ?? null,
      from: a.from_tick == null ? "" : String(a.from_tick),
      until: a.until_tick == null ? "" : String(a.until_tick),
      origin: dateDraft(dateUnits(a.descriptor), origin.components),
      offset: origin.offset,
    };
  });
}

/** The id a row is sent with: typed, else from its label, else positional. */
export function attachmentId(row: AttachmentDraft, index: number): string {
  if (row.id.trim()) return row.id.trim();
  return slugify(row.label) || (index === 0 ? DEFAULT_ID : `calendar-${index + 1}`);
}

export function libraryEntry(
  library: LibraryCalendar[],
  source: { owner: string; calendar: string } | null,
) {
  return source
    ? library.find((c) => c.owner === source.owner && c.id === source.calendar)
    : undefined;
}

/**
 * The descriptor a row reads as: what the book holds while it still names the
 * calendar it held and the update has not been taken; otherwise the library's.
 * Reading today's library entry for a held row would apply drift on a plain
 * save, re-dating a finished story through the one door every writer uses.
 */
export function rowDescriptor(
  row: AttachmentDraft,
  library: LibraryCalendar[],
): CalendarDescriptor | null {
  if (keepsHeld(row))
    return row.heldDescriptor ?? libraryEntry(library, row.source)?.descriptor ?? null;
  return libraryEntry(library, row.source)?.descriptor ?? null;
}

const keepsHeld = (row: AttachmentDraft) =>
  Boolean(
    row.held &&
    row.source &&
    row.held.owner === row.source.owner &&
    row.held.calendar === row.source.calendar,
  ) && !row.tookUpdate;

/**
 * The source to send: the held revision only while this is still the calendar
 * the book had and the update was not taken -- "keep mine". Anything else is a
 * fresh attach, and omitting the revision asks for the current entry.
 */
export function sourceToSend(row: AttachmentDraft): CalendarSource | null {
  if (!row.source) return null;
  return {
    ...row.source,
    rev: keepsHeld(row) ? (row.held?.rev ?? null) : null,
  } as CalendarSource;
}

/** The library's newer revision of a held calendar, if there is one to offer. */
export function updateOffer(
  row: AttachmentDraft,
  library: LibraryCalendar[],
): LibraryCalendar | null {
  if (!keepsHeld(row) || row.held?.rev == null) return null;
  const latest = libraryEntry(library, row.source);
  return latest && latest.rev > row.held.rev ? latest : null;
}

const isEarth = (descriptor: CalendarDescriptor | null) => descriptor?.kind === "gregorian";

export function toTick(raw: string): number | null {
  if (!raw.trim()) return null;
  const value = Number(raw);
  return Number.isInteger(value) ? value : null;
}

/** The rows as the API takes them, primary first. */
export function attachmentsBody(
  rows: AttachmentDraft[],
  library: LibraryCalendar[],
): CalendarAttachment[] {
  return rows.map((row, index) => {
    const descriptor = rowDescriptor(row, library);
    return {
      id: attachmentId(row, index),
      label: row.label.trim(),
      source: sourceToSend(row) as CalendarSource,
      from_tick: toTick(row.from),
      until_tick: toTick(row.until),
      origin: isEarth(descriptor)
        ? composeOrigin(descriptor, row.origin, row.offset)
        : null,
    };
  });
}

// -- where the book meets Earth's timeline -----------------------------------------

const ORIGIN = /^(-?\d+)-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(.*))?$/;
const OFFSET = /^(Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;

export function splitOrigin(text: string | null): {
  components: Record<string, number> | null;
  offset: string;
} {
  const match = ORIGIN.exec(String(text ?? ""));
  if (!match) return { components: null, offset: "Z" };
  const [, year, month, day, hour, minute, offset] = match;
  const components: Record<string, number> = {
    year: Number(year),
    month: Number(month),
    day: Number(day),
  };
  if (hour !== undefined) {
    components.hour = Number(hour);
    components.minute = Number(minute);
  }
  return { components, offset: offset || "Z" };
}

/**
 * The origin as the API spells it, or null while any part is blank: an origin
 * may not name a period -- half filled, it would quietly become 1 January.
 */
export function composeOrigin(
  descriptor: CalendarDescriptor | null,
  typed: DateDraft,
  offset: string,
): string | null {
  const units = dateUnits(descriptor);
  const read = dateValue(units, typed);
  if ("error" in read || units.some((u) => read.date[u.name] === undefined)) return null;
  const { date } = read;
  const pad = (n: number | undefined, width: number) =>
    String(Math.abs(n ?? 0)).padStart(width, "0");
  const year = date.year ?? 0;
  const day = `${year < 0 ? "-" : ""}${pad(year, 4)}-${pad(date.month, 2)}-${pad(date.day, 2)}`;
  if (descriptor?.tick_unit === "day") return day;
  return `${day}T${pad(date.hour, 2)}:${pad(date.minute, 2)}${offset.trim() || "Z"}`;
}

function originProblems(
  row: AttachmentDraft,
  descriptor: CalendarDescriptor | null,
): string[] {
  if (!isEarth(descriptor)) return [];
  const read = dateValue(dateUnits(descriptor), row.origin);
  if ("error" in read) return [read.error];
  if (descriptor?.tick_unit !== "day" && !OFFSET.test(row.offset.trim())) {
    return ["Use Z for UTC, or a fixed offset like -08:00."];
  }
  return composeOrigin(descriptor, row.origin, row.offset)
    ? []
    : ["Say which Earth date this book's tick 0 fell on."];
}

/** Why the calendars cannot be saved. Mirrors the server and goes no further. */
export function attachmentProblems(
  rows: AttachmentDraft[],
  library: LibraryCalendar[],
): string[] {
  const found: string[] = [];
  const seen = new Set<string>();
  rows.forEach((row, index) => {
    const id = attachmentId(row, index);
    const where = row.label.trim() || id;
    if (seen.has(id))
      found.push(`Two calendars share the id “${id}”. Give one another name.`);
    seen.add(id);
    if (!row.source) found.push(`${where}: choose a calendar from your library.`);
    for (const problem of originProblems(row, rowDescriptor(row, library)))
      found.push(`${where}: ${problem}`);
    const from = toTick(row.from);
    const until = toTick(row.until);
    if (row.from.trim() && from === null)
      found.push(`${where}: “Kept from tick” must be a whole number.`);
    if (row.until.trim() && until === null)
      found.push(`${where}: “Until tick” must be a whole number.`);
    if (from !== null && until !== null && from >= until)
      found.push(`${where}: it would end before it began.`);
  });
  return found;
}

// -- arranging the rows -------------------------------------------------------------

export function moveRow<T>(rows: T[], index: number, delta: number): T[] {
  const target = index + delta;
  if (index < 0 || index >= rows.length || target < 0 || target >= rows.length) return rows;
  const next = [...rows];
  const [moved] = next.splice(index, 1);
  next.splice(target, 0, moved as T);
  return next;
}

/** The book's primary reckoning is its first: making one primary moves it to the top. */
export function makePrimary<T>(rows: T[], index: number): T[] {
  return moveRow(rows, index, -index);
}

/** A row's label after the writer types it, carrying the id along unless they took it over. */
export function relabel(row: AttachmentDraft, label: string): AttachmentDraft {
  return { ...row, label, id: row.idTouched ? row.id : slugify(label) };
}

/** A row naming `calendar`, labelled after it when the writer has not named it yet. */
export function choose(
  row: AttachmentDraft,
  calendar: LibraryCalendar | null,
): AttachmentDraft {
  const source = calendar ? { owner: calendar.owner, calendar: calendar.id } : null;
  const named = row.label.trim() ? row : relabel(row, calendar?.name ?? "");
  return { ...named, source, origin: emptyDate() };
}

/** How a calendar is offered: bare when its name is unique, owner-qualified when two share it. */
export function optionLabel(calendar: LibraryCalendar, library: LibraryCalendar[]): string {
  const clashes = library.filter((c) => c.name === calendar.name).length > 1;
  return clashes ? `${calendar.name} (${calendar.qualified_id})` : calendar.name;
}
