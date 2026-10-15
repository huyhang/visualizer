import type { CalendarDescriptor, TickLabel } from "../../api/types";
import { dateUnits, type DateDraft } from "../calendars";
import {
  UNSCHEDULED_HINT,
  dateBody,
  dateTicksFor,
  describeDates,
  describeTicks,
  intOrNull,
  labelsAreUseful,
  readingsAt,
  tickBody,
  withNulls,
} from "./timing";

const IMPERIAL: CalendarDescriptor = {
  base_unit: "hour",
  cycles: [
    { name: "day", size: 24 },
    { name: "month", size: 30 },
  ],
};
const units = dateUnits(IMPERIAL);
const date = (parts: Record<string, string>): DateDraft => ({ parts, era: "CE" });
const label = (
  tick: number,
  text: string,
  readings?: TickLabel["readings"],
): TickLabel => ({ tick, label: text, parts: [text], readings });

describe("intOrNull", () => {
  it.each<[string, number | null]>([
    ["", null],
    ["  ", null],
    ["42", 42],
    ["-3", -3],
  ])("reads %j", (raw, expected) => {
    expect(intOrNull(raw)).toBe(expected);
  });

  it("marks a fraction as not a number", () => {
    expect(intOrNull("2.5")).toBeNaN();
  });
});

describe("tickBody", () => {
  it.each<[string, string, ReturnType<typeof tickBody>]>([
    ["240", "264", { body: { start_tick: 240, end_tick: 264 } }],
    ["", "", { body: { start_tick: null, end_tick: null } }],
    ["5", "5", { body: { start_tick: 5, end_tick: 5 } }],
    ["1.5", "2", { error: "Ticks must be whole numbers." }],
    [
      "5",
      "",
      { error: "Give both ticks, or neither — a half-known timeframe is not supported." },
    ],
    ["9", "3", { error: "The start must not be after the end." }],
  ])("reads %j → %j", (start, end, expected) => {
    expect(tickBody(start, end)).toEqual(expected);
  });
});

describe("dateBody", () => {
  it.each<[string, DateDraft, DateDraft, ReturnType<typeof dateBody>]>([
    [
      "a pair of periods",
      date({ month: "1", day: "3" }),
      date({ month: "1", day: "4" }),
      { body: { start_date: { month: 1, day: 3 }, end_date: { month: 1, day: 4 } } },
    ],
    ["no timing at all", date({}), date({}), { body: null }],
    [
      "half a timeframe",
      date({ month: "1" }),
      date({}),
      { error: "Give both dates, or neither — a half-known timeframe is not supported." },
    ],
    [
      "a hole in a date",
      date({ month: "1", hour: "3" }),
      date({ month: "1" }),
      { error: "Fill in the month down to the hour, or leave the finer parts blank." },
    ],
  ])("reads %s", (_, start, end, expected) => {
    expect(dateBody(units, start, end)).toEqual(expected);
  });

  it("says an undated scene with null ticks, so a save un-schedules it", () => {
    expect(withNulls({ body: null })).toEqual({
      body: { start_tick: null, end_tick: null },
    });
    expect(withNulls({ error: "x" })).toEqual({ error: "x" });
  });
});

describe("labelsAreUseful", () => {
  it.each<[CalendarDescriptor | null, boolean]>([
    [null, false],
    [{ kind: "identity" }, false],
    [{ kind: "gregorian", tick_unit: "day" }, true],
    [IMPERIAL, true],
    [{ base_unit: "tick", cycles: [] }, false],
  ])("for %j", (calendar, expected) => {
    expect(labelsAreUseful(calendar)).toBe(expected);
  });
});

describe("describeTicks", () => {
  const labels = [label(240, "Day 11"), label(264, "Day 12")];
  it.each<[number | null, number | null, string]>([
    [240, 264, "Day 11 → Day 12 (24 hours)."],
    [240, 240, "Day 11 (a moment)."],
    [264, 240, "Day 12 is after Day 11 — the start must come first."],
    [240, null, "Starts Day 11 — but give an end too, or neither."],
    [null, 264, "Ends Day 12 — but give a start too, or neither."],
    [null, null, UNSCHEDULED_HINT],
    [7, 9, "7 → 9 (2 hours)."],
  ])("words %s → %s", (start, end, expected) => {
    expect(describeTicks(labels, start, end, IMPERIAL)).toBe(expected);
  });
});

describe("describeDates", () => {
  it("names the period and the ticks it became", () => {
    const resolved = {
      start_tick: 48,
      end_tick: 72,
      ticks: [label(48, "Day 3"), label(72, "Day 4")],
    };
    expect(describeDates(resolved, IMPERIAL)).toBe(
      "Day 3 → Day 4 (24 hours) — ticks 48 → 72.",
    );
  });
});

describe("readingsAt", () => {
  const both = [
    { calendar: "imperial", name: "Imperial", label: "Day 3" },
    { calendar: "earth", name: "Earth", label: "29 Feb 2024" },
  ];
  it.each<[TickLabel[], number | null, string[]]>([
    [[label(48, "Day 3", both)], 48, ["Imperial: Day 3", "Earth: 29 Feb 2024"]],
    [[label(48, "Day 3", both.slice(0, 1))], 48, []],
    [[], 48, []],
  ])("lists the readings in %j", (ticks, at, expected) => {
    expect(readingsAt(ticks, at)).toEqual(expected);
  });
});

describe("dateTicksFor", () => {
  it.each<[number, number, [number, number] | null]>([
    [48, 72, [48, 71]],
    [48, 49, [48, 48]],
    [48, 48, null],
  ])("shows %i–%i through %j", (start, end, expected) => {
    expect(dateTicksFor(start, end)).toEqual(expected);
  });
});
