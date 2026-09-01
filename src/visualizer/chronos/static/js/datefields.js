// A date, typed in one calendar's own units.
//
// One box per unit the calendar names, coarsest first, generated from
// `dateUnits` — so any invented calendar works with no per-calendar code here.
// Leaving the finer boxes blank is how a writer says "some time that day": the
// date then names the whole period, which is exactly what the server does with
// it. Leaving a *middle* one blank is a hole, and is reported rather than
// quietly dropped — silently discarding a day the writer typed would place the
// scene somewhere they never said.
//
// No arithmetic. Turning a date into a tick stays on the server, because a
// browser that disagreed with it about what "Day 12" means would be the worst
// possible bug in this feature.
//
// The era control is the one exception, and it is pure spelling rather than
// arithmetic: a calendar that counts backwards past its own year 1 says so in
// its units, and the writer picks "BCE" instead of typing a minus sign. What
// crosses the wire is still the plain integer every other calendar sends.

import { el } from "./dom.js";

const ERAS = ["CE", "BCE"];

const capitalize = (word) => String(word).charAt(0).toUpperCase() + String(word).slice(1);

// A select's shown value is whichever option carries `selected`, not a `value`
// attribute, so it is assigned afterwards -- the house rule that keeps a
// control from rendering blank over correct state (see test_ui_assets).
function eraChoice() {
  const choose = el("select", { class: "date-era", title: "Before or after year 1" },
    ERAS.map((value) => el("option", { value, text: value })));
  choose.value = ERAS[0];
  return choose;
}

export function dateFields(units) {
  const boxes = units.map((unit) => ({
    unit,
    input: el("input", {
      type: "text", inputmode: "numeric", class: "date-part",
      title: unit.max === null
        ? `${capitalize(unit.name)} — any whole number`
        : `${capitalize(unit.name)} ${unit.min}–${unit.max}`,
    }),
    era: unit.era ? eraChoice() : null,
  }));

  // "44 BCE" is what a writer reads and types; a date on the wire is a map of
  // plain integers counting 1, 0, -1 back through it. One conversion, said once
  // here, in both directions.
  const typed = (box, n) => (box.era && box.era.value === "BCE" ? 1 - n : n);
  const shown = (box, value) => {
    if (!box.era) return value;
    box.era.value = value > 0 ? "CE" : "BCE";
    return value > 0 ? value : 1 - value;
  };

  return {
    node: el("div", { class: "date-end" }, boxes.map(({ unit, input, era }) =>
      el("label", { class: "date-part" }, [
        el("span", { class: "date-part-name muted", text: capitalize(unit.name) }),
        input,
        era,
      ].filter(Boolean)))),
    // Everything a caller should listen to, not just the boxes: changing the
    // era changes the date as surely as retyping the year does.
    controls: boxes.flatMap(({ input, era }) => (era ? [input, era] : [input])),
    empty: () => boxes.every(({ input }) => input.value.trim() === ""),
    value() {
      const date = {};
      let gap = false;
      for (const box of boxes) {
        const raw = box.input.value.trim();
        if (raw === "") { gap = true; continue; }
        if (gap) {
          return { error: `Fill in the ${units[0].name} down to the ${box.unit.name}, `
            + "or leave the finer parts blank." };
        }
        const n = Number(raw);
        if (!Number.isInteger(n)) return { error: "Dates must be whole numbers." };
        date[box.unit.name] = typed(box, n);
      }
      return { date };
    },
    fill: (components) => {
      for (const box of boxes) {
        const value = components ? components[box.unit.name] : undefined;
        const missing = value === undefined || value === null;
        box.input.value = missing ? "" : String(shown(box, value));
        if (missing && box.era) box.era.value = "CE";
      }
    },
  };
}
