import { compactInline, logosToPm, MAX_TEXT, pmToLogos } from "./convert";
import { safeHref } from "./href";
import { uniqueIds } from "./ids";
import { locateAll, locateQuote } from "./locate";
import { blockText, wordCount } from "./text";
import { curlDocument, curlText, curlTypedMark, fixElisions } from "./typography";
import type { LogosDocument } from "./types";
import { doc, mention, para, pmDoc, text } from "../test/docs";

const roundTrip = (document: LogosDocument) =>
  pmToLogos(pmDoc(document).toJSON(), () => "new");

describe("round trip", () => {
  it.each<[string, LogosDocument]>([
    ["plain paragraphs", doc(para("a", text("One.")), para("b", text("Two.")))],
    ["an empty paragraph", doc(para("a"), para("b", text("After.")))],
    [
      "nested marks in Logos order",
      doc(para("a", text("plain "), text("both", "em", "strong"), text(" code", "code"))),
    ],
    ["every mark at once", doc(para("a", text("all", "em", "strong", "strike", "code")))],
    [
      "mentions, article links and links",
      doc(
        para(
          "a",
          mention("Lyra"),
          text(" met "),
          {
            type: "article_link",
            text: "the Gate",
            ref: { database: "ember", collection: "places", id: "gate" },
          },
          text(" via "),
          { type: "link", href: "https://example.org/x", text: "a link" },
        ),
      ),
    ],
    [
      "hard breaks",
      doc(para("a", text("Line one"), { type: "hard_break" }, text("Line two"))),
    ],
    [
      "headings at each level",
      doc(
        { type: "heading", id: "h1", level: 1, content: [text("Part")] },
        { type: "heading", id: "h2", level: 2, content: [text("Chapter")] },
        { type: "heading", id: "h3", level: 3, content: [text("Scene")] },
      ),
    ],
    [
      "both kinds of list",
      doc(
        {
          type: "bullet_list",
          id: "l1",
          content: [
            { type: "list_item", content: [text("tea")] },
            { type: "list_item", content: [mention("Lyra")] },
          ],
        },
        { type: "ordered_list", id: "l2", content: [{ type: "list_item", content: [] }] },
      ),
    ],
    ["curly quotes kept", doc(para("a", text("“Don’t,” she said.")))],
  ])("keeps %s exactly", (_name, document) => {
    expect(roundTrip(document)).toEqual(document);
  });

  it.each<[string, LogosDocument, LogosDocument]>([
    [
      "marks in another order come back in Logos order",
      doc(
        para("a", { type: "text", text: "x", marks: [{ type: "strong" }, { type: "em" }] }),
      ),
      doc(para("a", text("x", "em", "strong"))),
    ],
    [
      "runs differing only in words merge",
      doc(para("a", text("one "), text("two"))),
      doc(para("a", text("one two"))),
    ],
    [
      "two pieces of one mention merge",
      doc(para("a", mention("Ly"), mention("ra"))),
      doc(para("a", mention("Lyra"))),
    ],
    [
      "an empty list gets one empty item",
      doc({ type: "bullet_list", id: "l", content: [] }),
      doc({ type: "bullet_list", id: "l", content: [{ type: "list_item", content: [] }] }),
    ],
    [
      "straight quotes are curled as the server curls them",
      doc(para("a", text(`"Don't," she said.`))),
      doc(para("a", text("“Don’t,” she said."))),
    ],
  ])("canonicalises: %s", (_name, given, expected) => {
    expect(roundTrip(given)).toEqual(expected);
  });

  it("gives an empty document one empty paragraph to type into", () => {
    expect(logosToPm(doc(), () => "fresh")).toEqual({
      type: "doc",
      content: [{ type: "paragraph", attrs: { id: "fresh" } }],
    });
  });

  it("renames a repeated id and fills a missing one, first holder keeping it", () => {
    let n = 0;
    const json = {
      type: "doc",
      content: [
        {
          type: "paragraph",
          attrs: { id: "a" },
          content: [{ type: "text", text: "One." }],
        },
        {
          type: "paragraph",
          attrs: { id: "a" },
          content: [{ type: "text", text: "Two." }],
        },
        {
          type: "paragraph",
          attrs: { id: null },
          content: [{ type: "text", text: "Three." }],
        },
      ],
    };
    const ids = pmToLogos(json, () => `new-${(n += 1)}`).content.map((block) => block.id);
    expect(ids).toEqual(["a", "new-1", "new-2"]);
  });

  it("cuts a run longer than the server takes into pieces it accepts", () => {
    const long = "x".repeat(MAX_TEXT * 2 + 5);
    const parts = compactInline([text(long)]);
    expect(parts.map((node) => ("text" in node ? node.text.length : 0))).toEqual([
      MAX_TEXT,
      MAX_TEXT,
      5,
    ]);
  });
});

describe("uniqueIds", () => {
  it.each<[(string | null)[], string[]]>([
    [
      ["a", "b"],
      ["a", "b"],
    ],
    [
      ["a", "a", "a"],
      ["a", "n1", "n2"],
    ],
    [
      [null, "", "  "],
      ["n1", "n2", "n3"],
    ],
  ])("%j becomes %j", (held, expected) => {
    let n = 0;
    expect(uniqueIds(held, () => `n${(n += 1)}`)).toEqual(expected);
  });
});

describe("safeHref", () => {
  it.each<[string | null, string | null]>([
    ["https://example.org", "https://example.org"],
    ["http://example.org/a", "http://example.org/a"],
    ["/logos/?book=x", "/logos/?book=x"],
    ["//evil.example", null],
    ["javascript:alert(1)", null],
    ["mailto:a@b.c", null],
    ["", null],
    [null, null],
  ])("%j -> %j", (given, expected) => expect(safeHref(given)).toBe(expected));
});

describe("text", () => {
  it("joins list items with a space and counts mentions as words", () => {
    const block = {
      type: "bullet_list" as const,
      id: "l",
      content: [
        { type: "list_item" as const, content: [text("tea")] },
        { type: "list_item" as const, content: [mention("Lyra"), text("'s cup")] },
      ],
    };
    expect(blockText(block)).toBe("tea Lyra's cup");
    // Run by run, as the server counts: "Lyra" and "'s cup" are three words.
    expect(wordCount(doc(block, para("p", text("two words"))))).toBe(6);
  });

  it("gives a hard break no text, as the server does", () => {
    expect(blockText(para("a", text("one"), { type: "hard_break" }, text("two")))).toBe(
      "onetwo",
    );
  });
});

describe("locateQuote", () => {
  it.each<[string, string, string, string | null]>([
    ["an exact phrase", "She lifted the teapot.", "lifted the teapot", "lifted the teapot"],
    ["a phrase that is gone", "She lifted the kettle.", "lifted the teapot", null],
    ["straight marks against curly prose", "“Don’t,” she said.", `"Don't,"`, "“Don’t,”"],
    [
      "a coach excerpt cut with an ellipsis",
      "A very long sentence goes on.",
      "A very long…",
      "A very long",
    ],
    ["collapsed whitespace", "one  two\nthree", "one two three", "one  two\nthree"],
    ["an empty quote", "anything", "", null],
  ])("%s", (_name, haystack, quote, expected) => {
    const span = locateQuote(haystack, quote);
    expect(span ? haystack.slice(span.start, span.end) : null).toBe(expected);
  });
});

describe("locateAll", () => {
  it.each<[string, string, string, [number, number][]]>([
    [
      "every time it comes",
      "very well. very well.",
      "very well",
      [
        [0, 9],
        [11, 20],
      ],
    ],
    [
      "overlapping places",
      "aaa",
      "aa",
      [
        [0, 2],
        [1, 3],
      ],
    ],
    [
      "loosely, as locateQuote does",
      "“No,” he said. “No,” she said.",
      `"No,"`,
      [
        [0, 5],
        [15, 20],
      ],
    ],
    ["nowhere", "She lifted the kettle.", "teapot", []],
    ["an empty quote", "anything", "", []],
  ])("%s", (_name, haystack, quote, expected) => {
    expect(locateAll(haystack, quote).map((s) => [s.start, s.end])).toEqual(expected);
  });
});

describe("typography", () => {
  it("curls dialogue and apostrophes but leaves code alone", () => {
    const curled = curlDocument(
      doc(
        para(
          "a",
          text(`"Don't," she said. `),
          text(`print("don't")`, "code"),
          text(" 'Twas enough."),
        ),
      ),
    );
    const block = curled.content[0];
    expect(
      block && "content" in block && block.content.map((n) => ("text" in n ? n.text : "")),
    ).toEqual(["“Don’t,” she said. ", `print("don't")`, " ’Twas enough."]);
    expect(curlText("'Hello,' and can't")).toBe("‘Hello,’ and can’t");
  });

  it.each<[string, string]>([
    ["She said ", "“"],
    ["", "“"],
    ["(", "“"],
    ["She said “hello", "”"],
    ["end.", "”"],
  ])("a double quote typed after %j is %s", (before, expected) => {
    expect(curlTypedMark(before, '"')).toBe(expected);
  });

  it.each<[string, string]>([
    ["don", "’"],
    ["shootin", "’"],
    ["", "‘"],
    ["said ", "‘"],
  ])("a single quote typed after %j is %s", (before, expected) => {
    expect(curlTypedMark(before, "'")).toBe(expected);
  });

  it.each<[string, string]>([
    ["‘t", "‘t"],
    ["‘ti", "‘ti"],
    ["‘tis so", "’tis so"],
    ["‘Twas night", "’Twas night"],
    ["‘em all", "’em all"],
    ["rock ‘n’ roll", "rock ’n’ roll"],
    ["the ‘90s", "the ’90s"],
    ["‘Hello,’ she said", "‘Hello,’ she said"],
  ])("fixElisions(%j) is %j", (given, expected) => {
    expect(fixElisions(given)).toBe(expected);
  });
});
