import type { CalendarDescriptor, LibraryCalendar } from "../../api/types";
import { PRESETS } from "../calendars";
import {
  calendarBody,
  calendarFailure,
  calendarFormProblems,
  cycleSteps,
  libraryOrder,
  matchesCalendar,
  moveCycle,
  type CalendarFormDraft,
} from "./calendarForm";

const draft = (over: Partial<CalendarFormDraft> = {}): CalendarFormDraft => ({
  name: "Imperial Reckoning",
  id: "imperial",
  notes: "Kept in the capital.",
  calendar: PRESETS[1]!.draft(),
  ...over,
});

describe("calendarBody", () => {
  it("sends the trimmed name, the notes and the descriptor -- never the id", () => {
    expect(calendarBody(draft({ name: "  Imperial  " }))).toEqual({
      name: "Imperial",
      notes: "Kept in the capital.",
      descriptor: {
        base_unit: "day",
        epoch_label: "",
        cycles: [
          { name: "month", size: 30 },
          { name: "year", size: 12 },
        ],
      },
    });
  });

  it("sends Earth as Earth", () => {
    expect(
      calendarBody(draft({ calendar: { kind: "gregorian", tickUnit: "hour" } })).descriptor,
    ).toEqual({
      kind: "gregorian",
      tick_unit: "hour",
    });
  });
});

describe("calendarFormProblems", () => {
  it.each<[string, Partial<CalendarFormDraft>, string[]]>([
    ["a complete draft", {}, []],
    ["no name", { name: " " }, ["Give the calendar a name."]],
    ["no id", { id: "" }, ["Give the calendar an id."]],
    [
      "a broken cycle",
      {
        calendar: {
          kind: "mixed_radix",
          baseUnit: "hour",
          epochLabel: "",
          cycles: [{ name: "day", size: "x" }],
        },
      },
      ["“day” needs a whole size of 1 or more."],
    ],
  ])("%s", (_, over, expected) => {
    expect(calendarFormProblems(draft(over))).toEqual(expected);
  });
});

describe("calendarFailure", () => {
  it.each<[string | null, number | null, string]>([
    [
      "ALREADY_EXISTS",
      409,
      "You already have a calendar with the id “imperial”. Choose another.",
    ],
    [
      "REVISION_CONFLICT",
      409,
      "Someone else changed this calendar — reload before saving.",
    ],
    ["INVALID_CALENDAR", 400, "fallback"],
  ])("%s / %s", (code, status, expected) => {
    expect(calendarFailure(code, status, "imperial", "fallback")).toBe(expected);
  });
});

describe("matchesCalendar", () => {
  const cal = {
    name: "Imperial Reckoning",
    qualified_id: "mara/imperial",
    notes: "Kept in the capital.",
  };
  it.each<[string, boolean]>([
    ["", true],
    ["imperial", true],
    ["capital mara", true],
    ["elvish", false],
  ])("filter %j", (query, expected) => {
    expect(matchesCalendar(cal, query)).toBe(expected);
  });
});

describe("cycleSteps", () => {
  it("draws a fantasy calendar as a chain, smallest first", () => {
    const hours: CalendarDescriptor = {
      base_unit: "hour",
      cycles: [
        { name: "day", size: 24 },
        { name: "month", size: 30 },
      ],
    };
    expect(cycleSteps(hours)).toEqual([
      { kind: "unit", name: "hour" },
      { kind: "size", size: 24 },
      { kind: "unit", name: "day" },
      { kind: "size", size: 30 },
      { kind: "unit", name: "month" },
    ]);
  });

  it.each<[CalendarDescriptor | null]>([
    [null],
    [{ kind: "gregorian", tick_unit: "day" }],
    [{ base_unit: "x", cycles: [] }],
  ])("draws nothing for %j", (descriptor) => {
    expect(cycleSteps(descriptor)).toEqual([]);
  });
});

describe("moveCycle", () => {
  const cycles = [
    { name: "a", size: "1" },
    { name: "b", size: "2" },
    { name: "c", size: "3" },
  ];
  it.each<[number, number, string[]]>([
    [0, 1, ["b", "a", "c"]],
    [2, -1, ["a", "c", "b"]],
    [0, -1, ["a", "b", "c"]],
    [2, 1, ["a", "b", "c"]],
  ])("moves %i by %i", (index, delta, expected) => {
    expect(moveCycle(cycles, index, delta).map((c) => c.name)).toEqual(expected);
  });
});

describe("libraryOrder", () => {
  const cal = (owner: string, name: string) => ({ owner, name }) as LibraryCalendar;
  it("lists your own calendars before shared ones, each by name", () => {
    const ordered = libraryOrder(
      [cal("ivo", "Alpha"), cal("mara", "Zeta"), cal("mara", "Beta")],
      "mara",
    );
    expect(ordered.map((c) => `${c.owner}:${c.name}`)).toEqual([
      "mara:Beta",
      "mara:Zeta",
      "ivo:Alpha",
    ]);
  });
});
