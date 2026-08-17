// The vocabulary of book calendars. No DOM, no api — pure functions over a
// descriptor and over the draft a form edits into one.
//
// A *descriptor* is what the API stores on a book (design §4.1):
//
//   {base_unit: "hour", cycles: [{name: "day", size: 24}, …], epoch_label: "AF"}
//
// Cycles are ordered smallest first and nest over the base unit. `null` means
// the book has no calendar and ticks read as their integer selves.
//
// A *draft* is the same thing mid-edit: sizes are still the strings a text input
// holds, and any field may be half-typed. `descriptorFrom` is the one-way door
// between them.
//
// This module is deliberately separate from the field that edits it. A shared
// calendar library — one named descriptor attached to many books — is the
// planned next step, and a picker over saved calendars needs exactly these
// helpers (the hint line, the problem list, the presets) without dragging in an
// inline editor's markup.

// -- descriptors -------------------------------------------------------------

export function descriptorFrom(draft) {
  return {
    base_unit: draft.baseUnit.trim(),
    cycles: draft.cycles.map((c) => ({ name: c.name.trim(), size: Number(c.size) })),
    epoch_label: draft.epochLabel.trim(),
  };
}

export function draftFrom(descriptor) {
  if (!descriptor || !(descriptor.cycles || []).length) return PRESETS[0].draft();
  return {
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
      baseUnit: "day",
      epochLabel: "",
      cycles: [{ name: "month", size: "30" }, { name: "year", size: "12" }],
    }),
  },
  {
    key: "blank",
    label: "Something else",
    draft: () => ({ baseUnit: "tick", epochLabel: "", cycles: [{ name: "cycle", size: "10" }] }),
  },
];

export function emptyCycle() {
  return { name: "", size: "" };
}

// -- what a writer needs told -------------------------------------------------

export function plural(word) {
  return /s$/.test(word) ? word : `${word}s`;
}

// A plain-language reading of the descriptor: "Ticks are hours: 24 hours to a
// day, 30 days to a month, 12 months to a year." Just naming the cycles — no
// arithmetic, so there is nothing here to fall out of step with the server's
// codec, which remains the only thing that turns a tick into a label.
export function calendarHint(calendar) {
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
export function dateUnits(calendar) {
  if (!calendar || calendar.kind === "identity") return [];
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
