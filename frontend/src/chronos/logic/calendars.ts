// The vocabulary of calendars: pure functions over a descriptor and over the
// draft a form edits into one. Ported from the classic page's calendars.js.
//
// A descriptor is what the API stores. A fantasy one spells out its cycles,
// smallest first: `{base_unit: "hour", cycles: [{name: "day", size: 24}, …]}`.
// An Earth one names only how long a tick is: `{kind: "gregorian", tick_unit}`.
// A draft is the same mid-edit, sizes still the strings an input holds.
//
// No arithmetic: turning a date into a tick stays on the server, so there is
// nothing here to fall out of step with its codec.

import type { CalendarDescriptor } from "../api/types";

export const GREGORIAN_TICK_UNITS = ["day", "hour", "minute"] as const;
export type GregorianTickUnit = (typeof GREGORIAN_TICK_UNITS)[number];

export interface CycleDraft {
  name: string;
  size: string;
}

export type CalendarDraft =
  | { kind: "gregorian"; tickUnit: string }
  | { kind: "mixed_radix"; baseUnit: string; epochLabel: string; cycles: CycleDraft[] };

export function descriptorFrom(draft: CalendarDraft): CalendarDescriptor {
  if (draft.kind === "gregorian") {
    return { kind: "gregorian", tick_unit: draft.tickUnit as GregorianTickUnit };
  }
  return {
    base_unit: draft.baseUnit.trim(),
    cycles: draft.cycles.map((c) => ({ name: c.name.trim(), size: Number(c.size) })),
    epoch_label: draft.epochLabel.trim(),
  };
}

export const PRESETS: { key: string; label: string; draft: () => CalendarDraft }[] = [
  {
    key: "hours",
    label: "Hours, days, months, years",
    draft: () => ({
      kind: "mixed_radix",
      baseUnit: "hour",
      epochLabel: "",
      cycles: [
        { name: "day", size: "24" },
        { name: "month", size: "30" },
        { name: "year", size: "12" },
      ],
    }),
  },
  {
    key: "days",
    label: "Days, months, years",
    draft: () => ({
      kind: "mixed_radix",
      baseUnit: "day",
      epochLabel: "",
      cycles: [
        { name: "month", size: "30" },
        { name: "year", size: "12" },
      ],
    }),
  },
  {
    key: "blank",
    label: "Something else",
    draft: () => ({
      kind: "mixed_radix",
      baseUnit: "tick",
      epochLabel: "",
      cycles: [{ name: "cycle", size: "10" }],
    }),
  },
];

/**
 * A draft of `descriptor`. Earth is recognised by `kind`, not by shape: it has
 * no cycles, and falling through to a preset would silently turn a writer's
 * Earth calendar into thirty-day months on the next save.
 */
export function draftFrom(
  descriptor: CalendarDescriptor | null | undefined,
): CalendarDraft {
  if (descriptor?.kind === "gregorian")
    return { kind: "gregorian", tickUnit: descriptor.tick_unit || "day" };
  if (!descriptor || !(descriptor.cycles ?? []).length) return PRESETS[0]!.draft();
  return {
    kind: "mixed_radix",
    baseUnit: descriptor.base_unit || "tick",
    epochLabel: descriptor.epoch_label || "",
    cycles: (descriptor.cycles ?? []).map((c) => ({ name: c.name, size: String(c.size) })),
  };
}

export const emptyCycle = (): CycleDraft => ({ name: "", size: "" });

export const pluralUnit = (word: string) => (/s$/.test(word) ? word : `${word}s`);

/** What one tick is called. */
export function tickName(calendar: CalendarDescriptor | null | undefined): string {
  if (!calendar) return "tick";
  return calendar.tick_unit || calendar.base_unit || "tick";
}

/** "Ticks are hours: 24 hours to a day, 30 days to a month." Naming only. */
export function calendarHint(calendar: CalendarDescriptor | null | undefined): string {
  if (calendar?.kind === "gregorian") {
    return (
      `Ticks are ${pluralUnit(tickName(calendar))}: Earth's own months, of 28, 29, ` +
      "30 or 31 days, and its leap years. No month length to choose."
    );
  }
  if (!calendar || calendar.kind === "identity" || !(calendar.cycles ?? []).length) {
    return "Ticks are plain whole numbers — pick a scale and stay consistent.";
  }
  const base = calendar.base_unit || "tick";
  const steps: string[] = [];
  let below = base;
  for (const cycle of calendar.cycles ?? []) {
    steps.push(`${cycle.size} ${pluralUnit(below)} to a ${cycle.name}`);
    below = cycle.name;
  }
  return `Ticks are ${pluralUnit(base)}: ${steps.join(", ")}.`;
}

export interface DateUnit {
  name: string;
  min: number;
  /** null for the open-ended top cycle. */
  max: number | null;
  /** Counted both ways past year 1, so written with an era rather than a minus sign. */
  era?: boolean;
}

const GREGORIAN_UNITS: DateUnit[] = [
  { name: "year", min: 1, max: null, era: true },
  { name: "month", min: 1, max: 12 },
  { name: "day", min: 1, max: 31 },
  { name: "hour", min: 0, max: 23 },
  { name: "minute", min: 0, max: 59 },
];

/**
 * The units a date is written in, coarsest first. Empty means "this calendar
 * cannot be written in": no calendar, or one naming two units alike, which a
 * date keyed by name could not tell apart.
 */
export function dateUnits(calendar: CalendarDescriptor | null | undefined): DateUnit[] {
  if (!calendar || calendar.kind === "identity") return [];
  if (calendar.kind === "gregorian") {
    const depth = (GREGORIAN_TICK_UNITS as readonly string[]).indexOf(tickName(calendar));
    return depth < 0 ? [] : GREGORIAN_UNITS.slice(0, depth + 3).map((u) => ({ ...u }));
  }
  const cycles = calendar.cycles ?? [];
  if (!cycles.length) return [];
  const ordered = [...cycles].reverse();
  const units: DateUnit[] = ordered.map((cycle, i) => ({
    name: cycle.name,
    min: 1,
    max: i === 0 ? null : (ordered[i - 1]?.size ?? null),
  }));
  units.push({
    name: calendar.base_unit || "tick",
    min: 0,
    max: (ordered[ordered.length - 1]?.size ?? 1) - 1,
  });
  const distinct = new Set(units.map((u) => u.name.trim().toLowerCase()));
  return distinct.size === units.length ? units : [];
}

/**
 * Why this draft cannot be saved yet. Mirrors the server's own check and goes
 * no further: refusing what the API would accept is worse than letting a 400 through.
 */
export function calendarProblems(draft: CalendarDraft): string[] {
  if (draft.kind === "gregorian") {
    return (GREGORIAN_TICK_UNITS as readonly string[]).includes(draft.tickUnit)
      ? []
      : ["Choose whether one tick is a day, an hour or a minute."];
  }
  const problems: string[] = [];
  if (!draft.baseUnit.trim()) problems.push("Name the base unit — what one tick is.");
  if (!draft.cycles.length) problems.push("A calendar needs at least one cycle.");
  draft.cycles.forEach((cycle, i) => {
    const named = cycle.name.trim();
    const where = named ? `“${named}”` : `Cycle ${i + 1}`;
    if (!named) problems.push(`${where} needs a name.`);
    const size = Number(cycle.size);
    if (cycle.size.trim() === "" || !Number.isInteger(size) || size < 1) {
      problems.push(`${where} needs a whole size of 1 or more.`);
    }
  });
  return problems;
}

// -- dates as typed --------------------------------------------------------------

export const ERAS = ["CE", "BCE"] as const;
export type Era = (typeof ERAS)[number];

/** One date as a form holds it: the typed text per unit, and the era where there is one. */
export interface DateDraft {
  parts: Record<string, string>;
  era: Era;
}

export const emptyDate = (): DateDraft => ({ parts: {}, era: "CE" });

/**
 * The date a draft names, or why it names none. Blank finer parts name the
 * whole period ("some time that day"); a blank part *between* filled ones is a
 * hole, reported rather than dropped. "44 BCE" crosses the wire as -43.
 */
export function dateValue(
  units: DateUnit[],
  draft: DateDraft,
): { date: Record<string, number> } | { error: string } {
  const date: Record<string, number> = {};
  let gap = false;
  for (const unit of units) {
    const raw = (draft.parts[unit.name] ?? "").trim();
    if (raw === "") {
      gap = true;
      continue;
    }
    if (gap) {
      return {
        error: `Fill in the ${units[0]?.name} down to the ${unit.name}, or leave the finer parts blank.`,
      };
    }
    const n = Number(raw);
    if (!Number.isInteger(n)) return { error: "Dates must be whole numbers." };
    date[unit.name] = unit.era && draft.era === "BCE" ? 1 - n : n;
  }
  return { date };
}

export const dateEmpty = (units: DateUnit[], draft: DateDraft) =>
  units.every((u) => (draft.parts[u.name] ?? "").trim() === "");

/** A draft showing `components` (as the server's tick labels carry them). */
export function dateDraft(
  units: DateUnit[],
  components: Record<string, number> | null | undefined,
): DateDraft {
  const draft = emptyDate();
  for (const unit of units) {
    const value = components?.[unit.name];
    if (value === undefined || value === null) continue;
    if (unit.era) {
      draft.era = value > 0 ? "CE" : "BCE";
      draft.parts[unit.name] = String(value > 0 ? value : 1 - value);
    } else {
      draft.parts[unit.name] = String(value);
    }
  }
  return draft;
}
