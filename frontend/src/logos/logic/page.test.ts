import { lookupText } from "../hooks/useAkasha";
import { usesDrawers } from "./layout";
import { memoryStore } from "./preferences";
import {
  applyReadingSettings,
  readingSettings,
  READER_SETTINGS_KEY,
} from "./readingSettings";
import { parseRef } from "./refs";
import { parseRoute } from "./route";

describe("parseRoute", () => {
  it.each<[string, object | null]>([
    [
      "?book=b&volume=v&section=s&mode=write",
      { book: "b", volume: "v", section: "s", draft: null, block: null, panel: null },
    ],
    [
      "?book=b&volume=v&section=s&draft=d2&block=p4",
      { draft: "d2", block: "p4", panel: null },
    ],
    ["?book=b&volume=v&section=s&coach=1", { panel: "coach" }],
    ["?book=b&volume=v&section=s&panel=editor", { panel: "editor" }],
    ["?book=b&volume=v&section=s&panel=nonsense", { panel: null }],
    ["?book=b&volume=v", null],
  ])("%s", (search, expected) => {
    const route = parseRoute(search);
    if (expected === null) expect(route).toBeNull();
    else expect(route).toMatchObject(expected);
  });
});

describe("reading settings", () => {
  it.each<[string | null, object]>([
    [null, { typeface: "serif", leading: "normal", measure: "medium", align: "left" }],
    [
      '{"typeface":"sans","measure":"wide","mode":"full"}',
      { typeface: "sans", leading: "normal", measure: "wide", align: "left" },
    ],
    [
      '{"typeface":"comic"}',
      { typeface: "serif", leading: "normal", measure: "medium", align: "left" },
    ],
    [
      "not json",
      { typeface: "serif", leading: "normal", measure: "medium", align: "left" },
    ],
  ])("from %j", (raw, expected) => {
    const store = memoryStore(raw === null ? {} : { [READER_SETTINGS_KEY]: raw });
    expect(readingSettings(store)).toEqual(expected);
  });

  it("puts them where reader.css looks for them", () => {
    const element = document.createElement("html");
    applyReadingSettings(element, {
      typeface: "sans",
      leading: "relaxed",
      measure: "narrow",
      align: "justify",
    });
    expect(element.dataset).toMatchObject({
      typeface: "sans",
      leading: "relaxed",
      measure: "narrow",
      align: "justify",
    });
  });
});

describe("lookupText", () => {
  it.each<[string, string | null]>([
    ["  Lin\n Qingyu ", "Lin Qingyu"],
    ["", null],
    ["   ", null],
    ["x".repeat(201), null],
  ])("%j -> %j", (selected, expected) => expect(lookupText(selected)).toBe(expected));
});

describe("parseRef", () => {
  it.each<[string, object | null]>([
    ["ember/characters/lin", { database: "ember", collection: "characters", id: "lin" }],
    ["ember/characters", null],
    ["a/b/c/d", null],
    ["a//c", null],
  ])("%j", (ref, expected) => expect(parseRef(ref)).toEqual(expected));
});

describe("usesDrawers", () => {
  it.each<[number, number, boolean]>([
    [1224, 16, false], // a laptop beside the full rail: three columns
    [1032, 16, false], // exactly 64.5rem
    [1031, 16, true],
    [1224, 22, true], // the same laptop at the largest text size: drawers
    [390, 16, true],
    [1000, 0, false], // no measurement yet
  ])("%ipx at %ipx a rem: drawers=%s", (width, rem, expected) => {
    expect(usesDrawers(width, rem)).toBe(expected);
  });
});
