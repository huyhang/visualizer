import type { CalendarDescriptor } from "../api/types";
import {
  PRESETS,
  calendarHint,
  calendarProblems,
  dateDraft,
  dateEmpty,
  dateUnits,
  dateValue,
  descriptorFrom,
  draftFrom,
  tickName,
  type CalendarDraft,
  type DateDraft,
} from "./calendars";

const IMPERIAL: CalendarDescriptor = {
  base_unit: "hour",
  cycles: [
    { name: "day", size: 24 },
    { name: "month", size: 30 },
    { name: "year", size: 12 },
  ],
  epoch_label: "AF",
};
const EARTH_DAYS: CalendarDescriptor = { kind: "gregorian", tick_unit: "day" };

describe("drafts and descriptors", () => {
  it("round-trips a fantasy calendar", () => {
    expect(descriptorFrom(draftFrom(IMPERIAL))).toEqual(IMPERIAL);
  });

  it("keeps Earth as Earth rather than falling back to a preset", () => {
    expect(draftFrom(EARTH_DAYS)).toEqual({ kind: "gregorian", tickUnit: "day" });
    expect(descriptorFrom(draftFrom(EARTH_DAYS))).toEqual(EARTH_DAYS);
  });

  it.each<[CalendarDescriptor | null]>([[null], [{ base_unit: "tick", cycles: [] }]])(
    "starts from the first preset when there is nothing to edit (%j)",
    (descriptor) => {
      expect(draftFrom(descriptor)).toEqual(PRESETS[0]?.draft());
    },
  );

  it("trims what was typed and reads sizes as numbers", () => {
    const draft: CalendarDraft = {
      kind: "mixed_radix",
      baseUnit: " hour ",
      epochLabel: " AF ",
      cycles: [{ name: " day ", size: "24" }],
    };
    expect(descriptorFrom(draft)).toEqual({
      base_unit: "hour",
      epoch_label: "AF",
      cycles: [{ name: "day", size: 24 }],
    });
  });
});

describe("calendarHint", () => {
  it.each<[CalendarDescriptor | null, string]>([
    [
      IMPERIAL,
      "Ticks are hours: 24 hours to a day, 30 days to a month, 12 months to a year.",
    ],
    [null, "Ticks are plain whole numbers — pick a scale and stay consistent."],
    [
      { kind: "identity" },
      "Ticks are plain whole numbers — pick a scale and stay consistent.",
    ],
  ])("reads %j", (calendar, hint) => {
    expect(calendarHint(calendar)).toBe(hint);
  });

  it("explains Earth without a month length to choose", () => {
    expect(calendarHint(EARTH_DAYS)).toMatch(/^Ticks are days: Earth's own months/);
  });
});

describe("tickName", () => {
  it.each<[CalendarDescriptor | null, string]>([
    [null, "tick"],
    [IMPERIAL, "hour"],
    [{ kind: "gregorian", tick_unit: "minute" }, "minute"],
  ])("names a tick of %j", (calendar, expected) => {
    expect(tickName(calendar)).toBe(expected);
  });
});

describe("dateUnits", () => {
  it("lists a fantasy calendar's units coarsest first, the top open-ended", () => {
    expect(dateUnits(IMPERIAL)).toEqual([
      { name: "year", min: 1, max: null },
      { name: "month", min: 1, max: 12 },
      { name: "day", min: 1, max: 30 },
      { name: "hour", min: 0, max: 23 },
    ]);
  });

  it.each<[CalendarDescriptor, string[]]>([
    [EARTH_DAYS, ["year", "month", "day"]],
    [
      { kind: "gregorian", tick_unit: "minute" },
      ["year", "month", "day", "hour", "minute"],
    ],
  ])("slices Earth to its precision (%j)", (calendar, names) => {
    expect(dateUnits(calendar).map((u) => u.name)).toEqual(names);
  });

  it.each<[CalendarDescriptor | null]>([
    [null],
    [{ kind: "identity" }],
    [{ base_unit: "day", cycles: [{ name: "Day", size: 7 }] }],
  ])("offers no date entry for %j", (calendar) => {
    expect(dateUnits(calendar)).toEqual([]);
  });
});

describe("calendarProblems", () => {
  it.each<[CalendarDraft, string[]]>([
    [{ kind: "gregorian", tickUnit: "hour" }, []],
    [
      { kind: "gregorian", tickUnit: "week" },
      ["Choose whether one tick is a day, an hour or a minute."],
    ],
    [PRESETS[0]!.draft(), []],
    [
      { kind: "mixed_radix", baseUnit: "", epochLabel: "", cycles: [] },
      ["Name the base unit — what one tick is.", "A calendar needs at least one cycle."],
    ],
    [
      {
        kind: "mixed_radix",
        baseUnit: "hour",
        epochLabel: "",
        cycles: [{ name: "", size: "0" }],
      },
      ["Cycle 1 needs a name.", "Cycle 1 needs a whole size of 1 or more."],
    ],
    [
      {
        kind: "mixed_radix",
        baseUnit: "hour",
        epochLabel: "",
        cycles: [{ name: "day", size: "2.5" }],
      },
      ["“day” needs a whole size of 1 or more."],
    ],
  ])("%j", (draft, problems) => {
    expect(calendarProblems(draft)).toEqual(problems);
  });
});

describe("dates as typed", () => {
  const units = dateUnits(IMPERIAL);
  const earth = dateUnits(EARTH_DAYS);
  const draft = (parts: Record<string, string>, era: "CE" | "BCE" = "CE"): DateDraft => ({
    parts,
    era,
  });

  it.each<[string, DateDraft, ReturnType<typeof dateValue>]>([
    [
      "a whole date",
      draft({ year: "1", month: "2", day: "3", hour: "4" }),
      { date: { year: 1, month: 2, day: 3, hour: 4 } },
    ],
    [
      "a period: the finer parts left blank",
      draft({ year: "1", month: "2" }),
      { date: { year: 1, month: 2 } },
    ],
    ["nothing at all", draft({}), { date: {} }],
    [
      "a hole in the middle",
      draft({ year: "1", day: "3" }),
      { error: "Fill in the year down to the day, or leave the finer parts blank." },
    ],
    ["a fraction", draft({ year: "1.5" }), { error: "Dates must be whole numbers." }],
  ])("reads %s", (_, typed, expected) => {
    expect(dateValue(units, typed)).toEqual(expected);
  });

  it.each<[DateDraft, Record<string, number>]>([
    [draft({ year: "44" }, "BCE"), { year: -43 }],
    [draft({ year: "1" }, "BCE"), { year: 0 }],
    [draft({ year: "2024" }), { year: 2024 }],
  ])("spells an era as a plain integer on the wire (%j)", (typed, date) => {
    expect(dateValue(earth, typed)).toEqual({ date });
  });

  it.each<[Record<string, number>, DateDraft]>([
    [{ year: -43, month: 3 }, draft({ year: "44", month: "3" }, "BCE")],
    [{ year: 2024 }, draft({ year: "2024" })],
  ])("shows %j as a writer would type it", (components, expected) => {
    expect(dateDraft(earth, components)).toEqual(expected);
  });

  it("knows an untouched date when it sees one", () => {
    expect(dateEmpty(units, draft({ year: " " }))).toBe(true);
    expect(dateEmpty(units, draft({ hour: "0" }))).toBe(false);
  });
});
