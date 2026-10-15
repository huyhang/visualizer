import type { Book } from "../../api/types";
import { book as bookFixture } from "../../test/fixtures";
import {
  bookBody,
  bookDraft,
  bookFailure,
  bookProblems,
  countPhrase,
  needsTypedConfirmation,
  retitle,
  type BookDraft,
} from "./bookForm";

const CAL = [
  { id: "imperial", label: "I", source: { owner: "mara", calendar: "imperial", rev: 1 } },
];

describe("bookDraft", () => {
  it("edits what the book holds, its id fixed", () => {
    expect(bookDraft(bookFixture())).toEqual({
      title: "The Ember Pact",
      id: "ember-pact",
      idTouched: true,
      overview: "A seal, a road and a crown.",
      world: "ember-pact",
      terminus: "coronation",
    });
  });

  it.each<[{ database: string }[], string]>([
    [[], ""],
    [[{ database: "only" }], "only"],
    [[{ database: "a" }, { database: "b" }], ""],
  ])("takes the only world as the default (%j)", (worlds, world) => {
    expect(bookDraft(null, worlds).world).toBe(world);
  });
});

describe("retitle", () => {
  it.each<[boolean, string]>([
    [false, "the-salt-road"],
    [true, "mine"],
  ])("follows the title unless the id was taken over (%s)", (touched, id) => {
    const draft: BookDraft = { ...bookDraft(null), id: "mine", idTouched: touched };
    expect(retitle(draft, "The Salt Road").id).toBe(id);
  });
});

describe("bookBody", () => {
  it("resends every stored field on an edit, so a full replace loses nothing", () => {
    expect(bookBody(bookDraft(bookFixture()), CAL, true)).toEqual({
      title: "The Ember Pact",
      overview: "A seal, a road and a crown.",
      calendars: CAL,
      world: "ember-pact",
      terminus: "coronation",
    });
  });

  it.each<[string, Partial<Book>, Record<string, unknown>]>([
    ["no world is said as null", { world: null }, { world: null }],
    ["no ending is said as null", { terminus: null }, { terminus: null }],
  ])("%s", (_, over, expected) => {
    expect(bookBody(bookDraft(bookFixture(over)), [], true)).toMatchObject(expected);
  });

  it("names no ending when creating: there are no scenes to end at", () => {
    expect(bookBody({ ...bookDraft(null), title: " New " }, [], false)).toEqual({
      title: "New",
      overview: "",
      calendars: [],
      world: null,
    });
  });
});

describe("bookProblems", () => {
  it.each<[Partial<BookDraft>, string[]]>([
    [{ title: "T", id: "t" }, []],
    [{ title: " ", id: "t" }, ["Give the book a title."]],
    [{ title: "T", id: "" }, ["Give the book an id."]],
  ])("%j", (over, expected) => {
    expect(bookProblems({ ...bookDraft(null), ...over })).toEqual(expected);
  });
});

describe("bookFailure", () => {
  it.each<[string | null, number | null, string]>([
    ["ALREADY_EXISTS", 409, "A book with the id “salt” already exists. Choose another."],
    [
      "REVISION_CONFLICT",
      409,
      "Someone else changed this book — reload the page before saving.",
    ],
    [null, 500, "fallback"],
  ])("%s / %s", (code, status, expected) => {
    expect(bookFailure(code, status, "salt", "fallback")).toBe(expected);
  });
});

describe("deleting", () => {
  it.each<[number, number | null, string, boolean]>([
    [3, 17, "3 plotlines and 17 scenes", true],
    [1, 1, "1 plotline and 1 scene", true],
    [0, 4, "4 scenes", true],
    [2, null, "2 plotlines and every scene in it", true],
    [0, 0, "", false],
  ])("%i plotlines, %s scenes", (plotlines, scenes, phrase, gated) => {
    expect(countPhrase(plotlines, scenes)).toBe(phrase);
    expect(needsTypedConfirmation(plotlines, scenes)).toBe(gated);
  });
});
