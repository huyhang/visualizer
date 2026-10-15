// The library's calendar form and cards, as pure functions: what a save
// sends, what stops it, and how a calendar reads at a glance.
//
// A library entry is always a real calendar. "Plain numbers" is a book that
// attaches nothing, so there is no such thing to author here.

import type {
  CalendarDescriptor,
  LibraryCalendar,
  LibraryCalendarWrite,
} from "../../api/types";
import {
  calendarProblems,
  descriptorFrom,
  type CalendarDraft,
  type CycleDraft,
} from "../calendars";

export interface CalendarFormDraft {
  name: string;
  id: string;
  notes: string;
  calendar: CalendarDraft;
}

export function calendarBody(draft: CalendarFormDraft): LibraryCalendarWrite {
  return {
    name: draft.name.trim(),
    notes: draft.notes,
    descriptor: descriptorFrom(draft.calendar),
  };
}

/** Why the form cannot be saved yet: the name and id first, then the calendar itself. */
export function calendarFormProblems(draft: CalendarFormDraft): string[] {
  const out: string[] = [];
  if (!draft.name.trim()) out.push("Give the calendar a name.");
  if (!draft.id) out.push("Give the calendar an id.");
  return out.concat(calendarProblems(draft.calendar));
}

/** The refusal in the writer's words: a taken id is theirs to fix, so it names it. */
export function calendarFailure(
  code: string | null,
  status: number | null,
  id: string,
  fallback: string,
): string {
  if (code === "ALREADY_EXISTS")
    return `You already have a calendar with the id “${id}”. Choose another.`;
  if (status === 409) return "Someone else changed this calendar — reload before saving.";
  return fallback;
}

/** Whether a calendar answers the library's filter: every typed word, anywhere. */
export function matchesCalendar(
  calendar: Pick<LibraryCalendar, "name" | "qualified_id" | "notes">,
  query: string,
): boolean {
  const haystack =
    `${calendar.name} ${calendar.qualified_id} ${calendar.notes ?? ""}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(word));
}

export type CycleStep = { kind: "unit"; name: string } | { kind: "size"; size: number };

/**
 * A fantasy calendar as a chain to draw: hour, 24, day, 30, month. Naming
 * only, like `calendarHint`: there is no arithmetic here to disagree with the
 * server's codec. Empty for Earth and for plain ticks, which read otherwise.
 */
export function cycleSteps(descriptor: CalendarDescriptor | null | undefined): CycleStep[] {
  if (!descriptor || descriptor.kind === "gregorian" || !(descriptor.cycles ?? []).length)
    return [];
  const steps: CycleStep[] = [{ kind: "unit", name: descriptor.base_unit || "tick" }];
  for (const cycle of descriptor.cycles ?? []) {
    steps.push({ kind: "size", size: cycle.size }, { kind: "unit", name: cycle.name });
  }
  return steps;
}

/** The cycles with one moved by `delta` places, clamped at the ends. */
export function moveCycle(
  cycles: CycleDraft[],
  index: number,
  delta: number,
): CycleDraft[] {
  const target = index + delta;
  if (index < 0 || index >= cycles.length || target < 0 || target >= cycles.length)
    return cycles;
  const next = [...cycles];
  const [moved] = next.splice(index, 1);
  next.splice(target, 0, moved as CycleDraft);
  return next;
}

/** Own calendars first, then shared ones, each by name. */
export function libraryOrder(calendars: LibraryCalendar[], me: string): LibraryCalendar[] {
  return [...calendars].sort(
    (a, b) =>
      Number(a.owner !== me) - Number(b.owner !== me) || a.name.localeCompare(b.name),
  );
}
