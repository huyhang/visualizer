// When a scene happens: the one part of the scene form with two ways to say
// the same thing. Ported from the classic page's scenetiming.js.
//
// Ticks are what Chronos stores and every rule reads. Dates are what a writer
// thinks in, and are an input spelling only: the server resolves them before
// anything is saved. No calendar arithmetic happens here -- a browser that
// disagreed with the server about what "Day 12" means would be the worst
// possible bug in this feature -- so these helpers only read, check and word.

import type { CalendarDescriptor, DateValue, TickLabel } from "../../api/types";
import {
  dateEmpty,
  dateValue,
  pluralUnit,
  tickName,
  type DateDraft,
  type DateUnit,
} from "../calendars";

/** What a save sends for the timeframe. Nulls say "unscheduled": a PUT replaces, so silence would keep old ticks. */
export type TimeframeBody =
  | { start_tick: number | null; end_tick: number | null }
  | { start_date: DateValue; end_date: DateValue };

export type Read<T> = { body: T } | { error: string };

/** A whole number, null for an empty box, NaN for anything else. */
export function intOrNull(raw: string): number | null {
  const text = raw.trim();
  if (text === "") return null;
  const n = Number(text);
  return Number.isInteger(n) ? n : NaN;
}

/** The two tick boxes as the API takes them, or why they cannot be sent. */
export function tickBody(
  startText: string,
  endText: string,
): Read<{ start_tick: number | null; end_tick: number | null }> {
  const start = intOrNull(startText);
  const end = intOrNull(endText);
  if (Number.isNaN(start) || Number.isNaN(end))
    return { error: "Ticks must be whole numbers." };
  if ((start === null) !== (end === null)) {
    return {
      error: "Give both ticks, or neither — a half-known timeframe is not supported.",
    };
  }
  if (start !== null && end !== null && start > end)
    return { error: "The start must not be after the end." };
  return { body: { start_tick: start, end_tick: end } };
}

/** The two dates as the API takes them; a null body is "no timing", a legitimate answer. */
export function dateBody(
  units: DateUnit[],
  start: DateDraft,
  end: DateDraft,
): Read<{ start_date: DateValue; end_date: DateValue } | null> {
  const from = dateValue(units, start);
  const to = dateValue(units, end);
  if ("error" in from) return from;
  if ("error" in to) return to;
  const startEmpty = dateEmpty(units, start);
  const endEmpty = dateEmpty(units, end);
  if (startEmpty && endEmpty) return { body: null };
  if (startEmpty || endEmpty) {
    return {
      error: "Give both dates, or neither — a half-known timeframe is not supported.",
    };
  }
  return { body: { start_date: from.date, end_date: to.date } };
}

/** What a save sends from the date side: "neither date" is said as null ticks. */
export function withNulls(
  read: Read<{ start_date: DateValue; end_date: DateValue } | null>,
): Read<TimeframeBody> {
  if ("error" in read) return read;
  return { body: read.body ?? { start_tick: null, end_tick: null } };
}

/** Whether asking the server for labels would tell the writer anything: with no calendar the label is the number. */
export function labelsAreUseful(calendar: CalendarDescriptor | null | undefined): boolean {
  if (!calendar || calendar.kind === "identity") return false;
  return calendar.kind === "gregorian" || (calendar.cycles ?? []).length > 0;
}

const labelOf = (labelled: TickLabel[], tick: number) =>
  labelled.find((t) => t.tick === tick)?.label ?? String(tick);

/** The live hint for typed ticks, in the book's own words. */
export function describeTicks(
  labelled: TickLabel[],
  start: number | null,
  end: number | null,
  calendar: CalendarDescriptor | null | undefined,
): string {
  if (start === null && end !== null)
    return `Ends ${labelOf(labelled, end)} — but give a start too, or neither.`;
  if (end === null && start !== null)
    return `Starts ${labelOf(labelled, start)} — but give an end too, or neither.`;
  if (start === null || end === null) return UNSCHEDULED_HINT;
  if (start > end)
    return `${labelOf(labelled, start)} is after ${labelOf(labelled, end)} — the start must come first.`;
  if (start === end) return `${labelOf(labelled, start)} (a moment).`;
  return `${labelOf(labelled, start)} → ${labelOf(labelled, end)} (${end - start} ${pluralUnit(tickName(calendar))}).`;
}

/** The live hint for typed dates: the period it landed on, and the ticks it became. */
export function describeDates(
  resolved: { start_tick: number; end_tick: number; ticks: TickLabel[] },
  calendar: CalendarDescriptor | null | undefined,
): string {
  const { start_tick: start, end_tick: end, ticks } = resolved;
  const span = `${end - start} ${pluralUnit(tickName(calendar))}`;
  return `${labelOf(ticks, start)} → ${labelOf(ticks, end)} (${span}) — ticks ${start} → ${end}.`;
}

export const UNSCHEDULED_HINT = "No timing yet — you can place this scene later.";

/** The same tick in every calendar the book keeps, worth showing only when there are two or more. */
export function readingsAt(ticks: TickLabel[], at: number | null): string[] {
  const entry = ticks.find((t) => t.tick === at) ?? ticks[0];
  const readings = entry?.readings ?? [];
  return readings.length < 2 ? [] : readings.map((r) => `${r.name}: ${r.label}`);
}

/**
 * The ticks to ask labels for when showing a span as dates. The end tick is
 * exclusive but a date box names the period the scene covers, so it shows the
 * last tick *inside* the scene -- filling it from the end itself would grow the
 * scene by a tick every time it was opened and saved untouched. A zero-length
 * span names no period and stays in ticks (null).
 */
export function dateTicksFor(start: number, end: number): [number, number] | null {
  return end <= start ? null : [start, end - 1];
}
