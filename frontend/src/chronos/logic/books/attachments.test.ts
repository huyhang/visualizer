import type {
  CalendarAttachment,
  CalendarDescriptor,
  LibraryCalendar,
} from "../../api/types";
import {
  attachmentId,
  attachmentProblems,
  attachmentsBody,
  blankAttachment,
  choose,
  composeOrigin,
  draftsFrom,
  makePrimary,
  moveRow,
  optionLabel,
  relabel,
  rowDescriptor,
  sourceToSend,
  splitOrigin,
  updateOffer,
  type AttachmentDraft,
} from "./attachments";

const HOURS: CalendarDescriptor = {
  base_unit: "hour",
  cycles: [{ name: "day", size: 24 }],
};
const HOURS_V2: CalendarDescriptor = {
  base_unit: "hour",
  cycles: [{ name: "day", size: 20 }],
};
const EARTH_DAY: CalendarDescriptor = { kind: "gregorian", tick_unit: "day" };
const EARTH_HOUR: CalendarDescriptor = { kind: "gregorian", tick_unit: "hour" };

const lib = (
  id: string,
  descriptor: CalendarDescriptor,
  rev = 1,
  owner = "mara",
  name = id,
): LibraryCalendar => ({
  kind: "calendar",
  id,
  owner,
  qualified_id: `${owner}/${id}`,
  name,
  descriptor,
  rev,
});
const LIBRARY = [
  lib("imperial", HOURS_V2, 3),
  lib("earth", EARTH_DAY),
  lib("clock", EARTH_HOUR),
];

const held = (over: Partial<CalendarAttachment> = {}): CalendarAttachment => ({
  id: "imperial",
  label: "Imperial Reckoning",
  descriptor: HOURS,
  source: { owner: "mara", calendar: "imperial", rev: 2 },
  ...over,
});

const row = (over: Partial<AttachmentDraft> = {}): AttachmentDraft => ({
  ...blankAttachment(),
  ...over,
});

describe("draftsFrom", () => {
  it("puts the primary first and keeps what the book holds", () => {
    const [first, second] = draftsFrom([
      held({ id: "elvish", label: "Elvish" }),
      held({ primary: true, from_tick: 5 }),
    ]);
    expect(first).toMatchObject({
      id: "imperial",
      from: "5",
      held: { rev: 2 },
      heldDescriptor: HOURS,
    });
    expect(second?.id).toBe("elvish");
  });

  it.each<[string, string, boolean]>([
    ["an id derived from its label follows it", "imperial-reckoning", false],
    ["an id of the writer's own is kept", "imperial", true],
  ])("%s", (_, id, touched) => {
    expect(draftsFrom([held({ id })])[0]?.idTouched).toBe(touched);
  });

  it("reads an Earth origin back into the boxes", () => {
    const [earth] = draftsFrom([
      held({
        descriptor: EARTH_DAY,
        origin: "-0043-03-15",
        source: { owner: "mara", calendar: "earth", rev: 1 },
      }),
    ]);
    expect(earth?.origin).toEqual({
      parts: { year: "44", month: "3", day: "15" },
      era: "BCE",
    });
  });
});

describe("attachmentId", () => {
  it.each<[Partial<AttachmentDraft>, number, string]>([
    [{ id: " elvish " }, 1, "elvish"],
    [{ label: "Elvish Count" }, 1, "elvish-count"],
    [{}, 0, "default"],
    [{}, 2, "calendar-3"],
  ])("%j at %i", (over, index, expected) => {
    expect(attachmentId(row(over), index)).toBe(expected);
  });
});

describe("sourceToSend and the update offer", () => {
  const [kept] = draftsFrom([held()]);
  it("keeps the held revision on a plain save", () => {
    expect(sourceToSend(kept!)).toEqual({ owner: "mara", calendar: "imperial", rev: 2 });
    expect(rowDescriptor(kept!, LIBRARY)).toEqual(HOURS);
  });

  it("offers the library's newer revision, and taking it asks for the current entry", () => {
    expect(updateOffer(kept!, LIBRARY)?.rev).toBe(3);
    const took = { ...kept!, tookUpdate: true };
    expect(sourceToSend(took)).toEqual({ owner: "mara", calendar: "imperial", rev: null });
    expect(rowDescriptor(took, LIBRARY)).toEqual(HOURS_V2);
    expect(updateOffer(took, LIBRARY)).toBeNull();
  });

  it.each<[string, LibraryCalendar[]]>([
    ["the library is at the same revision", [lib("imperial", HOURS, 2)]],
    ["the calendar left the library", []],
  ])("offers nothing when %s", (_, library) => {
    expect(updateOffer(kept!, library)).toBeNull();
  });

  it("treats a different calendar as a fresh attach", () => {
    const switched = choose(kept!, LIBRARY[1]!);
    expect(sourceToSend(switched)).toEqual({ owner: "mara", calendar: "earth", rev: null });
  });

  it("sends nothing for a row with no calendar chosen", () => {
    expect(sourceToSend(row())).toBeNull();
  });
});

describe("attachmentsBody", () => {
  it("sends every row primary first, with its era and no descriptor", () => {
    const rows = [
      row({
        label: "Imperial",
        source: { owner: "mara", calendar: "imperial" },
        from: "",
        until: "300",
      }),
    ];
    expect(attachmentsBody(rows, LIBRARY)).toEqual([
      {
        id: "imperial",
        label: "Imperial",
        source: { owner: "mara", calendar: "imperial", rev: null },
        from_tick: null,
        until_tick: 300,
        origin: null,
      },
    ]);
  });

  it("composes an Earth origin for an Earth calendar only", () => {
    const earth = row({
      source: { owner: "mara", calendar: "earth" },
      origin: { parts: { year: "2024", month: "2", day: "27" }, era: "CE" },
    });
    expect(attachmentsBody([earth], LIBRARY)[0]?.origin).toBe("2024-02-27");
  });
});

describe("origins", () => {
  it.each<
    [CalendarDescriptor, Record<string, string>, "CE" | "BCE", string, string | null]
  >([
    [EARTH_DAY, { year: "2024", month: "2", day: "27" }, "CE", "Z", "2024-02-27"],
    [EARTH_DAY, { year: "44", month: "3", day: "15" }, "BCE", "Z", "-0043-03-15"],
    [
      EARTH_HOUR,
      { year: "2024", month: "2", day: "27", hour: "6" },
      "CE",
      "-08:00",
      "2024-02-27T06:00-08:00",
    ],
    [
      EARTH_HOUR,
      { year: "2024", month: "2", day: "27", hour: "6" },
      "CE",
      " ",
      "2024-02-27T06:00Z",
    ],
    [EARTH_DAY, { year: "2024", month: "2" }, "CE", "Z", null],
  ])("composes %j %j %s", (descriptor, parts, era, offset, expected) => {
    expect(composeOrigin(descriptor, { parts, era }, offset)).toBe(expected);
  });

  it.each<[string | null, ReturnType<typeof splitOrigin>]>([
    ["2024-02-27", { components: { year: 2024, month: 2, day: 27 }, offset: "Z" }],
    [
      "2024-02-27T06:30-08:00",
      {
        components: { year: 2024, month: 2, day: 27, hour: 6, minute: 30 },
        offset: "-08:00",
      },
    ],
    [null, { components: null, offset: "Z" }],
    ["nonsense", { components: null, offset: "Z" }],
  ])("splits %j", (text, expected) => {
    expect(splitOrigin(text)).toEqual(expected);
  });
});

describe("attachmentProblems", () => {
  const imperial = { owner: "mara", calendar: "imperial" };
  it.each<[string, AttachmentDraft[], string[]]>([
    ["a sound row", [row({ label: "Imperial", source: imperial })], []],
    [
      "no calendar chosen",
      [row({ label: "Imperial" })],
      ["Imperial: choose a calendar from your library."],
    ],
    [
      "two rows with one id",
      [
        row({ label: "A", id: "x", source: imperial }),
        row({ label: "B", id: "x", source: imperial }),
      ],
      ["Two calendars share the id “x”. Give one another name."],
    ],
    [
      "a fractional tick",
      [row({ label: "I", source: imperial, from: "1.5" })],
      ["I: “Kept from tick” must be a whole number."],
    ],
    [
      "an era ending first",
      [row({ label: "I", source: imperial, from: "9", until: "3" })],
      ["I: it would end before it began."],
    ],
    [
      "an Earth calendar with no origin",
      [row({ label: "Earth", source: { owner: "mara", calendar: "earth" } })],
      ["Earth: Say which Earth date this book's tick 0 fell on."],
    ],
    [
      "a bad offset",
      [
        row({
          label: "Clock",
          source: { owner: "mara", calendar: "clock" },
          origin: { parts: { year: "1", month: "1", day: "1", hour: "0" }, era: "CE" },
          offset: "PST",
        }),
      ],
      ["Clock: Use Z for UTC, or a fixed offset like -08:00."],
    ],
  ])("%s", (_, rows, expected) => {
    expect(attachmentProblems(rows, LIBRARY)).toEqual(expected);
  });
});

describe("arranging rows", () => {
  it.each<[number, number, string[]]>([
    [0, 1, ["b", "a", "c"]],
    [1, -1, ["b", "a", "c"]],
    [2, 1, ["a", "b", "c"]],
  ])("moves %i by %i", (index, delta, expected) => {
    expect(moveRow(["a", "b", "c"], index, delta)).toEqual(expected);
  });

  it("makes a row primary by moving it to the top", () => {
    expect(makePrimary(["a", "b", "c"], 2)).toEqual(["c", "a", "b"]);
  });

  it("carries the id along with the label until it is taken over", () => {
    expect(relabel(row(), "Elvish Count").id).toBe("elvish-count");
    expect(relabel(row({ id: "elves", idTouched: true }), "Elvish Count").id).toBe("elves");
  });

  it("names an unnamed row after the calendar chosen for it", () => {
    expect(choose(row(), LIBRARY[0]!)).toMatchObject({
      label: "imperial",
      source: { owner: "mara", calendar: "imperial" },
    });
    expect(choose(row({ label: "Mine" }), LIBRARY[0]!).label).toBe("Mine");
  });
});

describe("optionLabel", () => {
  it("qualifies a name only when two calendars share it", () => {
    const a = lib("imperial", HOURS, 1, "mara", "Imperial");
    const b = lib("imperial", HOURS, 1, "ivo", "Imperial");
    expect(optionLabel(a, [a])).toBe("Imperial");
    expect(optionLabel(b, [a, b])).toBe("Imperial (ivo/imperial)");
  });
});
