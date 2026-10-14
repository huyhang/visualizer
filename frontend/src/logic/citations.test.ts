import { describe, expect, it } from "vitest";
import type { Fact, SourceRow } from "../api/types";
import {
  citedBy,
  citedByLine,
  factAsWikitext,
  isCitation,
  quotesFrom,
  sourceNumbers,
} from "./citations";
import { parseInline, parseLines } from "./wikitext";

describe("isCitation", () => {
  it.each([
    ["research-inbox/a", true],
    ["sources/a", true],
    ["characters/lin", false],
    ["song/sources/a", false],
    ["research-inboxed/a", false],
  ])("%s -> %s", (target, expected) => {
    expect(isCitation(target)).toBe(expected);
  });
});

const fact = (text: string, ...sources: string[]): Fact => ({
  text,
  check: "supported",
  citations: sources.map((source) => ({ source, quote: `${text} from ${source}` })),
});

describe("factAsWikitext", () => {
  it.each([
    [fact("Whisked.", "research-inbox/a"), "* Whisked. [[research-inbox/a]]"],
    [
      fact(" Two. ", "sources/a", "sources/b", "sources/a"),
      "* Two. [[sources/a]] [[sources/b]]",
    ],
    [fact("None."), "* None."],
  ])("%#", (input, expected) => {
    expect(factAsWikitext(input)).toBe(expected);
  });
});

describe("quotesFrom", () => {
  it("gathers one source's quotes across facts, without repeats", () => {
    const facts = [fact("A", "s/1"), fact("B", "s/2"), { ...fact("A", "s/1") }];
    expect(quotesFrom("s/1", facts)).toEqual(["A from s/1"]);
    expect(quotesFrom("s/3", facts)).toEqual([]);
  });
});

describe("sourceNumbers", () => {
  it("numbers sources in the draft's order", () => {
    const rows = ["x", "y"].map((ref) => ({ ref }) as SourceRow);
    expect([...sourceNumbers(rows)]).toEqual([
      ["x", 1],
      ["y", 2],
    ]);
  });
});

describe("citedBy", () => {
  it("finds citations inside formatting, once each, ignoring other links", () => {
    const inlines = parseInline(
      "'''a [[sources/x]]''' [[characters/lin]] [[research-inbox/y]] [[sources/x]]",
    );
    expect(citedBy(inlines)).toEqual(["sources/x", "research-inbox/y"]);
  });

  it("an image line cites nothing", () => {
    expect(citedByLine(parseLines(`{{image:${"c".repeat(32)}|left|30|x}}`)[0]!)).toEqual(
      [],
    );
  });
});
