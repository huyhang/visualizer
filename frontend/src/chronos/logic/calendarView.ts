// Which of a book's calendars the writer is reading through.
//
// A book may keep several parallel reckonings; switching changes what the
// dates say and nothing else, so it is a view preference rather than a route.
// It is remembered per book, under the classic page's own key, so the two
// pages agree on it. No formatting happens in the browser: labels come from
// the server's codec, and this only says which one to ask for.

import type { CalendarAttachment } from "../api/types";
import type { KeyValueStore } from "../deps";

export const CALENDAR_KEY = "chronos.calendarView";

function stored(store: KeyValueStore): Record<string, string> {
  try {
    const parsed: unknown = JSON.parse(store.get(CALENDAR_KEY) || "{}");
    return parsed && typeof parsed === "object" ? (parsed as Record<string, string>) : {};
  } catch {
    return {};
  }
}

/**
 * The remembered choice, validated against what the book has now: a calendar
 * detached since would otherwise make every read on the page a refusal.
 * Before the book has been read (`calendars` undefined) it is trusted, so the
 * first reads already ask for it -- not a round in the primary calendar, read
 * again a moment later.
 */
export function chosenCalendar(
  store: KeyValueStore,
  book: string,
  calendars: CalendarAttachment[] | undefined,
): string | null {
  const chosen = stored(store)[book];
  if (!chosen) return null;
  if (!calendars) return chosen;
  return calendars.some((c) => c.id === chosen) ? chosen : null;
}

/**
 * Remember `calendarId` for `book`. The primary is stored as no preference, so
 * a book is not pinned to whichever calendar happened to be first that day.
 */
export function chooseCalendar(
  store: KeyValueStore,
  book: string,
  calendarId: string | null,
  calendars: CalendarAttachment[] = [],
): void {
  const map = stored(store);
  if (calendarId && calendarId !== calendars[0]?.id) map[book] = calendarId;
  else delete map[book];
  store.set(CALENDAR_KEY, JSON.stringify(map));
}

/** "Kept from tick 100 until 300": why half a book reads "before Elvish Count". */
export function eraNote(
  calendar: Pick<CalendarAttachment, "from_tick" | "until_tick">,
): string {
  const { from_tick: from, until_tick: until } = calendar;
  const hasFrom = from !== null && from !== undefined;
  const hasUntil = until !== null && until !== undefined;
  if (hasFrom && hasUntil) return `Kept from tick ${from} until ${until}.`;
  if (hasFrom) return `Kept from tick ${from} onwards.`;
  if (hasUntil) return `Kept until tick ${until}.`;
  return "";
}
