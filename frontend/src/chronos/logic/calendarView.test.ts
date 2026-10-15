import type { CalendarAttachment } from "../api/types";
import { memoryStore } from "../test/memoryStore";
import { CALENDAR_KEY, chooseCalendar, chosenCalendar, eraNote } from "./calendarView";

const source = { owner: "mara", calendar: "x" };
const CALENDARS: CalendarAttachment[] = [
  { id: "imperial", label: "Imperial", source },
  { id: "earth", label: "Earth", source },
];

describe("chosenCalendar", () => {
  it.each<[string, string | undefined, string | null]>([
    ["nothing remembered", undefined, null],
    ["a calendar the book keeps", JSON.stringify({ b: "earth" }), "earth"],
    ["a calendar since detached", JSON.stringify({ b: "elvish" }), null],
    ["another book's choice", JSON.stringify({ other: "earth" }), null],
    ["unreadable storage", "{not json", null],
    ["a stored scalar", "7", null],
  ])("answers for %s", (_, raw, expected) => {
    const store = memoryStore(raw === undefined ? {} : { [CALENDAR_KEY]: raw });
    expect(chosenCalendar(store, "b", CALENDARS)).toBe(expected);
  });
});

describe("chooseCalendar", () => {
  it.each<[string, string | null, Record<string, string>]>([
    ["a secondary calendar is remembered", "earth", { b: "earth" }],
    ["the primary is stored as no preference", "imperial", {}],
    ["clearing forgets", null, {}],
  ])("%s", (_, choice, expected) => {
    const store = memoryStore({ [CALENDAR_KEY]: JSON.stringify({ b: "earth" }) });
    chooseCalendar(store, "b", choice, CALENDARS);
    expect(JSON.parse(store.data[CALENDAR_KEY] ?? "{}")).toEqual(expected);
  });

  it("leaves other books' choices alone", () => {
    const store = memoryStore({ [CALENDAR_KEY]: JSON.stringify({ other: "elvish" }) });
    chooseCalendar(store, "b", "earth", CALENDARS);
    expect(JSON.parse(store.data[CALENDAR_KEY] ?? "{}")).toEqual({
      other: "elvish",
      b: "earth",
    });
  });
});

describe("eraNote", () => {
  it.each<[number | null | undefined, number | null | undefined, string]>([
    [null, null, ""],
    [undefined, undefined, ""],
    [100, 300, "Kept from tick 100 until 300."],
    [0, null, "Kept from tick 0 onwards."],
    [null, 48, "Kept until tick 48."],
  ])("from %s until %s", (from, until, expected) => {
    expect(eraNote({ from_tick: from, until_tick: until })).toBe(expected);
  });
});
