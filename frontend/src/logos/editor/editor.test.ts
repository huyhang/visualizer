import { Slice } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import { doc, mention, para, pmDoc, schema, text } from "../test/docs";
import { makeEditor } from "../test/editor";
import { annotationState, decorate, place, type Annotation } from "./annotations";
import { minimalEdit } from "./fixes";
import { currentBlockStyle } from "./blockStyle";
import { mentionAt } from "./mentions";
import { blockAt, caretAt, caretPos, findBlock, quoteRange, textMap } from "./positions";
import { curlSlice, elisionsIn, typedText } from "./smartQuotes";

const listDoc = doc(para("p", text("Before.")), {
  type: "bullet_list",
  id: "l",
  content: [
    { type: "list_item", content: [text("tea")] },
    { type: "list_item", content: [mention("Lyra"), text(" pours")] },
  ],
});

/** Put the caret `offset` characters into block `id`. */
function caretIn(
  editor: ReturnType<typeof makeEditor>["editor"],
  id: string,
  offset: number,
) {
  const pos = caretPos(editor.state.doc, { block: id, offset });
  editor.view.dispatch(
    editor.state.tr.setSelection(TextSelection.create(editor.state.doc, pos!)),
  );
}

describe("positions", () => {
  it("maps a list's text, items joined by one space, onto positions", () => {
    const pm = pmDoc(listDoc);
    const block = findBlock(pm, "l")!;
    const map = textMap(block.node, block.pos);
    expect(map.text).toBe("tea Lyra pours");
    const range = quoteRange(pm, "l", "Lyra pours")!;
    expect(pm.textBetween(range.from, range.to)).toBe("Lyra pours");
  });

  it.each<[string, string, string | null]>([
    ["p", "Before", "Before"],
    ["l", "tea", "tea"],
    ["l", "coffee", null],
    ["missing", "Before", null],
  ])("finds %j / %j", (block, quote, expected) => {
    const pm = pmDoc(listDoc);
    const range = quoteRange(pm, block, quote);
    expect(range ? pm.textBetween(range.from, range.to) : null).toBe(expected);
  });

  it.each([0, 3, 7])(
    "a caret %i characters into a block survives a round trip",
    (offset) => {
      const pm = pmDoc(doc(para("a", text("One.")), para("b", text("Second one."))));
      const pos = caretPos(pm, { block: "b", offset })!;
      expect(caretAt(pm, pos)).toEqual({ block: "b", offset });
      expect(blockAt(pm, pos)?.node.attrs.id).toBe("b");
    },
  );

  it("puts a caret past the end of its block at the block's end", () => {
    const pm = pmDoc(doc(para("a", text("One."))));
    expect(caretPos(pm, { block: "a", offset: 99 })).toBe(5);
    expect(caretPos(pm, { block: "gone", offset: 0 })).toBeNull();
  });
});

describe("block ids", () => {
  it("renames the second half of a split paragraph, the first keeping its id", () => {
    const { editor, logos } = makeEditor(doc(para("a", text("One. Two."))));
    caretIn(editor, "a", 4);
    editor.commands.splitBlock();
    expect(logos().content.map((block) => block.id)).toEqual(["a", "new-1"]);
  });

  it("gives a pasted copy of a block a fresh id", () => {
    const { editor, logos } = makeEditor(doc(para("a", text("One."))));
    const own = editor.schema;
    const copy = own.nodes.paragraph!.create({ id: "a" }, own.text("Copy."));
    editor.view.dispatch(editor.state.tr.insert(editor.state.doc.content.size, copy));
    expect(logos().content.map((block) => block.id)).toEqual(["a", "new-1"]);
  });
});

describe("lists", () => {
  it("makes the touched paragraphs one list, keeping the first id, and back again", () => {
    const { editor, logos } = makeEditor(
      doc(para("a", text("One")), para("b", text("Two"))),
    );
    editor.commands.setTextSelection({ from: 2, to: 8 });
    editor.commands.toggleLogosList("bullet_list");
    expect(logos().content).toEqual([
      {
        type: "bullet_list",
        id: "a",
        content: [
          { type: "list_item", content: [text("One")] },
          { type: "list_item", content: [text("Two")] },
        ],
      },
    ]);
    editor.commands.toggleLogosList("bullet_list");
    expect(logos().content.map((block) => [block.type, block.id])).toEqual([
      ["paragraph", "a"],
      ["paragraph", "new-1"],
    ]);
  });

  it("turns a bullet list into a numbered one", () => {
    const { editor, logos } = makeEditor(listDoc);
    caretIn(editor, "l", 1);
    editor.commands.toggleLogosList("ordered_list");
    expect(logos().content[1]).toMatchObject({ type: "ordered_list", id: "l" });
  });

  it("leaves the list on Enter in an empty item", () => {
    const { editor, logos } = makeEditor(
      doc({
        type: "bullet_list",
        id: "l",
        content: [
          { type: "list_item", content: [text("one")] },
          { type: "list_item", content: [] },
          { type: "list_item", content: [text("three")] },
        ],
      }),
    );
    const second = editor.state.doc.child(0).child(0).nodeSize + 2;
    editor.commands.setTextSelection(second);
    expect(editor.commands.keyboardShortcut("Enter")).toBe(true);
    expect(logos().content.map((block) => block.type)).toEqual([
      "bullet_list",
      "paragraph",
      "bullet_list",
    ]);
  });

  it("takes the bullet off an item on Backspace at its start, keeping its words", () => {
    const { editor, logos } = makeEditor(listDoc);
    caretIn(editor, "l", 0);
    editor.commands.keyboardShortcut("Backspace");
    expect(logos().content.map((block) => block.type)).toEqual([
      "paragraph",
      "paragraph",
      "bullet_list",
    ]);
    expect(logos().content[1]).toMatchObject({ id: "l", content: [text("tea")] });
  });
});

describe("block style", () => {
  it.each<["p" | 1 | 2 | 3, string]>([
    [1, "heading"],
    [3, "heading"],
    ["p", "paragraph"],
  ])("style %j keeps the block's id", (style, type) => {
    const { editor, logos } = makeEditor(doc(para("a", text("Title"))));
    caretIn(editor, "a", 2);
    editor.commands.setBlockStyle(style);
    expect(logos().content[0]).toMatchObject({ type, id: "a" });
    expect(currentBlockStyle(editor.state)).toBe(style);
  });

  it("has no style inside a list", () => {
    const { editor } = makeEditor(listDoc);
    caretIn(editor, "l", 1);
    expect(currentBlockStyle(editor.state)).toBeNull();
  });
});

describe("smart quotes", () => {
  it.each<[string, string, string]>([
    ["She said ", '"', "“"],
    ["she said “hi", '"', "”"],
    ["don", "'", "’"],
    ["anything", "x", "x"],
  ])("after %j, typing %s lands %s", (before, typed, landed) => {
    expect(typedText(before, typed)).toBe(landed);
  });

  it("finds the elision a finished word completes", () => {
    expect(elisionsIn("and ‘tis")).toEqual([4]);
    expect(elisionsIn("‘Hello")).toEqual([]);
  });

  it("curls quotes as they are typed, and an elision once its word lands", () => {
    const { editor, type, logos } = makeEditor(doc(para("a")));
    caretIn(editor, "a", 0);
    type(`"Hi," she said. 'tis`);
    expect(logos().content[0]).toMatchObject({ content: [text("“Hi,” she said. ’tis")] });
  });

  it("leaves a quote typed inside code straight", () => {
    const { editor, type, logos } = makeEditor(doc(para("a", text("x", "code"))));
    caretIn(editor, "a", 1);
    type(`"`);
    expect(logos().content[0]).toMatchObject({ content: [text(`x"`, "code")] });
  });

  it("curls a pasted slice, but not its code", () => {
    const slice = new Slice(
      schema.nodes.paragraph!.create(null, [
        schema.text(`"Don't" `),
        schema.text(`say("x")`, [schema.marks.code!.create()]),
      ]).content,
      0,
      0,
    );
    const curled = curlSlice(slice);
    expect(curled.content.child(0).text).toBe("“Don’t” ");
    expect(curled.content.child(1).text).toBe(`say("x")`);
  });
});

describe("mentions", () => {
  it("links selected words without changing them, and unlinks them again", () => {
    const { editor, logos } = makeEditor(doc(para("a", text("Lyra waited."))));
    expect(
      editor.commands.linkMention(
        { from: 1, to: 5 },
        { database: "ember", collection: "characters", id: "lyra" },
      ),
    ).toBe(true);
    expect(logos().content[0]).toMatchObject({
      content: [mention("Lyra"), text(" waited.")],
    });
    const found = mentionAt(editor.state, 3)!;
    expect(found).toMatchObject({ id: "lyra", text: "Lyra", range: { from: 1, to: 5 } });
    editor.commands.unlinkMention(3);
    expect(logos().content[0]).toMatchObject({ content: [text("Lyra waited.")] });
  });

  it("will not link across two paragraphs", () => {
    const { editor } = makeEditor(doc(para("a", text("One")), para("b", text("Two"))));
    expect(
      editor.commands.linkMention(
        { from: 2, to: 8 },
        { database: "d", collection: "c", id: "i" },
      ),
    ).toBe(false);
  });
});

describe("fixes", () => {
  it("replaces the quoted words in one undoable step", () => {
    const { editor, logos } = makeEditor(
      doc(para("a", text("She lifted the teapot and poured."))),
    );
    expect(
      editor.commands.applyFix({
        blockId: "a",
        quote: "lifted the teapot",
        replacement: "whisked the tea",
      }),
    ).toBe(true);
    expect(logos().content[0]).toMatchObject({
      content: [text("She whisked the tea and poured.")],
    });
    editor.commands.undo();
    expect(logos().content[0]).toMatchObject({
      content: [text("She lifted the teapot and poured.")],
    });
  });

  it.each<[string, string, { start: number; end: number; insert: string }]>([
    ["lifted the teapot", "lifted the kettle", { start: 11, end: 0, insert: "kettle" }],
    ["Sir Aldric rode", "Then Sir Aldric rode", { start: 0, end: 15, insert: "Then " }],
    ["very very old", "very old", { start: 5, end: 3, insert: "" }],
    ["same", "same", { start: 4, end: 0, insert: "" }],
  ])("the smallest edit from %j to %j", (before, after, expected) => {
    expect(minimalEdit(before, after)).toEqual(expected);
  });

  it("keeps a linked name the fix does not change", () => {
    const { editor, logos } = makeEditor(
      doc(para("a", mention("Lyra"), text(" waited at the gate."))),
    );
    editor.commands.applyFix({
      blockId: "a",
      quote: "Lyra waited",
      replacement: "Then Lyra waited",
    });
    expect(logos().content[0]).toMatchObject({
      content: [text("Then "), mention("Lyra"), text(" waited at the gate.")],
    });
  });

  it("never takes in a hard break beside the words it changes", () => {
    const { editor, logos } = makeEditor(
      doc(para("a", text("one"), { type: "hard_break" }, text("two"))),
    );
    editor.commands.applyFix({ blockId: "a", quote: "onetwo", replacement: "onetwos" });
    expect(logos().content[0]).toMatchObject({
      content: [text("one"), { type: "hard_break" }, text("twos")],
    });
  });

  it("refuses a fix whose words are gone", () => {
    const { editor } = makeEditor(doc(para("a", text("Nothing here."))));
    expect(
      editor.commands.applyFix({ blockId: "a", quote: "teapot", replacement: "bowl" }),
    ).toBe(false);
  });

  it("selects the quoted words for a fix by hand", () => {
    const { editor } = makeEditor(doc(para("a", text("She lifted the teapot."))));
    editor.commands.selectQuote("a", "the teapot");
    const { from, to } = editor.state.selection;
    expect(editor.state.doc.textBetween(from, to)).toBe("the teapot");
  });
});

describe("annotations", () => {
  const issue = (
    id: string,
    blockId: string,
    quote: string,
    source: "coach" | "editor" = "editor",
  ): Annotation => ({
    id,
    source,
    kind: "prose",
    severity: "warning",
    blockId,
    quote,
  });

  it("places each annotation, or reports it unplaced", () => {
    const pm = pmDoc(doc(para("a", text("She lifted the teapot."))));
    const placement = place(pm, [issue("1", "a", "the teapot"), issue("2", "a", "kettle")]);
    expect(placement["1"]).toEqual({ from: 12, to: 22 });
    expect(placement["2"]).toBeNull();
  });

  it("draws an underline per placed annotation and one margin marker per block", () => {
    const pm = pmDoc(doc(para("a", text("She lifted the teapot."))));
    const all = [issue("1", "a", "lifted"), issue("2", "a", "teapot", "coach")];
    const set = decorate(pm, all, place(pm, all), "1");
    // Two underlines, and one margin marker for the paragraph they share.
    expect(set.find()).toHaveLength(3);
  });

  it("follows the words as the writer edits, and lets go when they are rewritten", () => {
    const { editor, bridge } = makeEditor(doc(para("a", text("She lifted the teapot."))));
    editor.commands.setAnnotations([issue("1", "a", "the teapot")]);
    expect(annotationState(editor.state)?.placement["1"]).toEqual({ from: 12, to: 22 });
    editor.commands.insertContentAt(1, "Then ");
    expect(annotationState(editor.state)?.placement["1"]).toEqual({ from: 17, to: 27 });
    editor.commands.applyFix({ blockId: "a", quote: "teapot", replacement: "bowl" });
    expect(annotationState(editor.state)?.placement["1"]).toBeNull();
    expect(bridge.onPlacement).toHaveBeenLastCalledWith({ "1": null });
  });

  it("never puts an annotation into the saved document or the undo history", () => {
    const { editor, logos } = makeEditor(doc(para("a", text("She lifted the teapot."))));
    const before = logos();
    editor.commands.setAnnotations([issue("1", "a", "teapot")]);
    editor.commands.setActiveAnnotation("1");
    expect(logos()).toEqual(before);
    expect(editor.can().undo()).toBe(false);
  });
});
