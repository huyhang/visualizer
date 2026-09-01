// The vocabulary of book calendars. No DOM, no api — pure functions over a
// descriptor and over the draft a form edits into one.
//
// A *descriptor* is what the API stores on a book (design §4.1). A fantasy one
// spells out its own fixed cycles:
//
//   {base_unit: "hour", cycles: [{name: "day", size: 24}, …], epoch_label: "AF"}
//
// Cycles are ordered smallest first and nest over the base unit. `null` means
// the book has no calendar and ticks read as their integer selves.
//
// An Earth one names only how long a tick is, because its month lengths are not
// a fact anyone gets to choose:
//
//   {kind: "gregorian", tick_unit: "day"}
//
// A *draft* is the same thing mid-edit: sizes are still the strings a text input
// holds, and any field may be half-typed. `descriptorFrom` is the one-way door
// between them. A draft says which `kind` it is building so that switching the
// type in the editor cannot leave half of the other one behind.
//
// This module is deliberately separate from the field that edits it. A shared
// calendar library — one named descriptor attached to many books — is the
// planned next step, and a picker over saved calendars needs exactly these
// helpers (the hint line, the problem list, the presets) without dragging in an
// inline editor's markup.

// -- descriptors -------------------------------------------------------------

// One tick is one of these. Earth's are fixed durations even though its months
// are not — that is the whole trick.
export const GREGORIAN_TICK_UNITS = ["day", "hour", "minute"];

export function descriptorFrom(draft) {
  if (draft.kind === "gregorian") {
    return { kind: "gregorian", tick_unit: draft.tickUnit };
  }
  return {
    base_unit: draft.baseUnit.trim(),
    cycles: draft.cycles.map((c) => ({ name: c.name.trim(), size: Number(c.size) })),
    epoch_label: draft.epochLabel.trim(),
  };
}

export function draftFrom(descriptor) {
  // Earth first, and by `kind` rather than by shape: it has no cycles, so the
  // fallback below would quietly hand back a fantasy preset — and saving that
  // would turn a writer's Earth calendar into thirty-day months without a word
  // on screen to say so.
  if (descriptor && descriptor.kind === "gregorian") {
    return { kind: "gregorian", tickUnit: descriptor.tick_unit || "day" };
  }
  if (!descriptor || !(descriptor.cycles || []).length) return PRESETS[0].draft();
  return {
    kind: "mixed_radix",
    baseUnit: descriptor.base_unit || "tick",
    epochLabel: descriptor.epoch_label || "",
    cycles: descriptor.cycles.map((c) => ({ name: c.name, size: String(c.size) })),
  };
}

// Starting points, so the common case is a click rather than a form. The first
// is the demo story's calendar; the last is for a writer whose world is not
// earth-shaped.
export const PRESETS = [
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
      cycles: [{ name: "month", size: "30" }, { name: "year", size: "12" }],
    }),
  },
  {
    key: "blank",
    label: "Something else",
    draft: () => ({
      kind: "mixed_radix", baseUnit: "tick", epochLabel: "",
      cycles: [{ name: "cycle", size: "10" }],
    }),
  },
];

export function emptyCycle() {
  return { name: "", size: "" };
}

// -- what a writer needs told -------------------------------------------------

export function plural(word) {
  return /s$/.test(word) ? word : `${word}s`;
}

// What one tick is called. A fantasy calendar names it; Earth's is fixed by the
// precision it was created at. Either way it is the word a span is counted in.
export function tickName(calendar) {
  if (!calendar) return "tick";
  return calendar.tick_unit || calendar.base_unit || "tick";
}

// A plain-language reading of the descriptor: "Ticks are hours: 24 hours to a
// day, 30 days to a month, 12 months to a year." Just naming the cycles — no
// arithmetic, so there is nothing here to fall out of step with the server's
// codec, which remains the only thing that turns a tick into a label.
export function calendarHint(calendar) {
  if (calendar && calendar.kind === "gregorian") {
    return `Ticks are ${plural(tickName(calendar))}: Earth's own months, of 28, 29, `
      + "30 or 31 days, and its leap years. No month length to choose.";
  }
  if (!calendar || calendar.kind === "identity" || !(calendar.cycles || []).length) {
    return "Ticks are plain whole numbers — pick a scale and stay consistent.";
  }
  const base = calendar.base_unit || "tick";
  const steps = [];
  let below = base;
  for (const cycle of calendar.cycles) {
    steps.push(`${cycle.size} ${plural(below)} to a ${cycle.name}`);
    below = cycle.name;
  }
  return `Ticks are ${plural(base)}: ${steps.join(", ")}.`;
}

// The units a date is written in, coarsest first — one entry per input the
// scene form offers, with the range the server will enforce.
//
// Naming only: which unit sits where, and how far each one counts. Turning a
// date into a tick stays on the server (see api.resolveDates), so there is no
// arithmetic here to fall out of step with the codec.
//
// An empty list means "this calendar cannot be written in", and is the one
// signal the form keys date entry off. Two cases give it: a book with no
// calendar (ticks are already the plainest thing to type), and a calendar that
// names two units alike — legal, but a date keyed by name could not say which
// was meant, so the server refuses one and the form must not offer one.
// Earth's units, deepest first. Sliced to whatever precision the calendar was
// created at, because a day-counting calendar has no hour to ask for.
const GREGORIAN_UNITS = [
  // Open-ended like any top cycle, and counted in both directions — so the box
  // carries an era rather than a minus sign. See `datefields.dateFields`.
  { name: "year", min: 1, max: null, era: true },
  { name: "month", min: 1, max: 12 },
  // The real ceiling is this month's own length, which nothing here can know
  // until a year and a month have been typed. The server applies it; naming 31
  // keeps the hint honest about the widest a month ever gets.
  { name: "day", min: 1, max: 31 },
  { name: "hour", min: 0, max: 23 },
  { name: "minute", min: 0, max: 59 },
];

export function dateUnits(calendar) {
  if (!calendar || calendar.kind === "identity") return [];
  if (calendar.kind === "gregorian") {
    const depth = GREGORIAN_TICK_UNITS.indexOf(tickName(calendar));
    return depth < 0 ? [] : GREGORIAN_UNITS.slice(0, depth + 3).map((u) => ({ ...u }));
  }
  const cycles = calendar.cycles || [];
  if (!cycles.length) return [];
  // Cycles are stored smallest first; a date is said largest first.
  const ordered = [...cycles].reverse();
  const units = ordered.map((cycle, i) => ({
    name: cycle.name,
    // A cycle counts 1..(how many of it fit in the one above). The topmost has
    // nothing above it and is open-ended, which is what lets a story run past
    // "Year 12" and lets Year 0 and below be the ticks before the epoch.
    min: 1,
    max: i === 0 ? null : ordered[i - 1].size,
  }));
  // The base unit reads 0-indexed, the way a clock does.
  units.push({ name: calendar.base_unit || "tick", min: 0, max: ordered[ordered.length - 1].size - 1 });
  const distinct = new Set(units.map((u) => String(u.name).trim().toLowerCase()));
  return distinct.size === units.length ? units : [];
}

// Why this draft cannot be saved yet, in the writer's words. Mirrors what
// `validation._check_calendar` enforces server-side and goes no further: a
// browser that refuses a descriptor the API would accept is a worse bug than one
// that lets a 400 through. Cycle names that repeat, or shadow the base unit, are
// legal and merely read oddly — `calendarHint` shows that better than a rule
// could say it.
export function calendarProblems(draft) {
  if (draft.kind === "gregorian") {
    // Nothing else to get wrong: the months are Earth's, and where this book
    // sits on Earth's timeline is asked for on the book, not here.
    return GREGORIAN_TICK_UNITS.includes(draft.tickUnit)
      ? [] : ["Choose whether one tick is a day, an hour or a minute."];
  }
  const problems = [];
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
