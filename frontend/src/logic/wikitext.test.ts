import { describe, expect, it } from "vitest";
import {
  formatImage,
  groupLines,
  parseInline,
  parseLines,
  plainText,
  type Inline,
} from "./wikitext";
import { isCitation } from "./citations";

describe("parseInline", () => {
  it.each<[string, Inline[]]>([
    ["plain", [{ kind: "text", text: "plain" }]],
    [
      "a [[x/y]] b",
      [
        { kind: "text", text: "a " },
        { kind: "link", target: "x/y", label: null },
        { kind: "text", text: " b" },
      ],
    ],
    ["[[x/y|Why]]", [{ kind: "link", target: "x/y", label: "Why" }]],
    ["[[x/y| ]]", [{ kind: "link", target: "x/y", label: null }]],
    ["'''bold'''", [{ kind: "bold", children: [{ kind: "text", text: "bold" }] }]],
    ["''it''", [{ kind: "italic", children: [{ kind: "text", text: "it" }] }]],
    [
      "'''see [[a/b]]'''",
      [
        {
          kind: "bold",
          children: [
            { kind: "text", text: "see " },
            { kind: "link", target: "a/b", label: null },
          ],
        },
      ],
    ],
  ])("%j", (text, expected) => {
    expect(parseInline(text)).toEqual(expected);
  });
});

describe("parseLines", () => {
  it.each([
    ["Para", "paragraph"],
    ["* item", "item"],
    ["== Head ==", "heading"],
    ["=== Sub ===", "heading"],
    [`{{image:${"a".repeat(32)}|right|40|A bowl}}`, "image"],
    [`{{image:${"a".repeat(32)}|full|50|bad}}`, "paragraph"],
    [`{{image:${"a".repeat(32)}|left|5|too small}}`, "paragraph"],
  ])("%j is a %s", (text, kind) => {
    expect(parseLines(text)[0]!.kind).toBe(kind);
  });

  it("skips blank lines and keeps each line's source", () => {
    const lines = parseLines("One\n\n  \n* two  \n");
    expect(lines.map((l) => l.source)).toEqual(["One", "* two"]);
  });

  it("reads a heading's level", () => {
    const [line] = parseLines("=== Deeper ===");
    expect(line).toMatchObject({ kind: "heading", level: 3 });
  });
});

describe("groupLines", () => {
  it("gathers consecutive items into one list", () => {
    const groups = groupLines(parseLines("P\n* a\n* b\nQ\n* c"));
    expect(groups.map((g) => (g.kind === "list" ? g.items.length : g.line.kind))).toEqual([
      "paragraph",
      2,
      "paragraph",
      1,
    ]);
  });
});

describe("plainText", () => {
  it.each([
    ["Tea was whisked [[research-inbox/a]].", "Tea was whisked."],
    ["'''Bold''' and [[song/characters/lin|Lin]]", "Bold and Lin"],
    ["See [[characters/lin-qingyu]] now", "See lin-qingyu now"],
    ["Two [[sources/a]] [[sources/b]] cites", "Two cites"],
  ])("%j -> %j", (text, expected) => {
    expect(plainText(parseInline(text), isCitation)).toBe(expected);
  });
});

describe("formatImage", () => {
  const id = "b".repeat(32);
  it.each([
    [{ align: "right", width: 40, caption: "Bowl" }, `{{image:${id}|right|40|Bowl}}`],
    [{ align: "full", width: 30, caption: "Wide" }, `{{image:${id}|full|100|Wide}}`],
    [{ align: "left", width: 3, caption: "a}}b\nc" }, `{{image:${id}|left|10|a} }b c}}`],
  ] as const)("%j", (image, expected) => {
    expect(formatImage({ mediaId: id, ...image })).toBe(expected);
  });

  it("round-trips through the parser", () => {
    const text = formatImage({
      mediaId: id,
      align: "center",
      width: 60,
      caption: "A bowl",
    });
    expect(parseLines(text)[0]).toMatchObject({
      kind: "image",
      mediaId: id,
      align: "center",
      width: 60,
      caption: "A bowl",
    });
  });
});
