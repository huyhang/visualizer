import { describe, expect, it } from "vitest";
import {
  addBlank,
  addedCount,
  addImage,
  addText,
  bodyOf,
  draftsOf,
  emptyComposition,
  hasImage,
  hasText,
  moveBlock,
  noteRequest,
  onExisting,
  onNew,
  pendingImages,
  problem,
  removeBlock,
  setTitle,
  updateBlock,
  withMedia,
  withoutBlocks,
  type Composition,
} from "./compose";

function ids() {
  let n = 0;
  return () => `b${++n}`;
}

const IMAGE = {
  draft: "tea",
  index: 0,
  caption: "A bowl",
  previewUrl: "/p",
  mediaId: null,
};
const MEDIA = "f".repeat(32);

function sample(): Composition {
  const newId = ids();
  let comp = setTitle(emptyComposition(), "Tea");
  comp = addText(comp, "* Whisked. [[research-inbox/a]]", "tea", newId);
  comp = addText(comp, "My own line.", null, newId);
  return addImage(comp, IMAGE, newId);
}

describe("adding", () => {
  it("adds text and images in order, and knows what is in", () => {
    const comp = sample();
    expect(comp.blocks.map((b) => b.kind)).toEqual(["text", "text", "image"]);
    expect(hasText(comp, "* Whisked. [[research-inbox/a]]")).toBe(true);
    expect(hasText(comp, "Other")).toBe(false);
    expect(hasImage(comp, "tea", 0)).toBe(true);
    expect(addedCount(comp)).toBe(3);
  });

  it.each(["", "   \n"])("ignores blank text %j", (text) => {
    expect(addText(emptyComposition(), text, "tea", ids()).blocks).toEqual([]);
  });

  it("does not add the same image twice", () => {
    const comp = sample();
    expect(addImage(comp, IMAGE, ids()).blocks).toHaveLength(3);
  });

  it("adds a blank block for the writer's own words, and says which", () => {
    const { comp, id } = addBlank(emptyComposition(), ids());
    expect(comp.blocks).toEqual([{ id, kind: "text", text: "", draft: null }]);
  });
});

describe("arranging", () => {
  it.each([
    ["b1", 1, ["b2", "b1", "b3"]],
    ["b3", -2, ["b3", "b1", "b2"]],
    ["b1", -1, ["b1", "b2", "b3"]],
    ["b3", 1, ["b1", "b2", "b3"]],
    ["nope", 1, ["b1", "b2", "b3"]],
  ])("moveBlock(%s, %i)", (id, delta, order) => {
    expect(moveBlock(sample(), id, delta).blocks.map((b) => b.id)).toEqual(order);
  });

  it("updates and removes blocks", () => {
    let comp = updateBlock(sample(), "b2", { text: "Changed." });
    expect(comp.blocks[1]).toMatchObject({ text: "Changed." });
    comp = removeBlock(comp, "b2");
    expect(comp.blocks.map((b) => b.id)).toEqual(["b1", "b3"]);
    expect(withoutBlocks(comp, new Set(["b1"])).blocks.map((b) => b.id)).toEqual(["b3"]);
  });
});

describe("switching what the note is", () => {
  const NOTE = { slug: "tea", rev: 7, title: "Tea", body: "What I knew." };

  it("opening an existing note puts its body first and keeps what was added", () => {
    const comp = onExisting(sample(), NOTE, () => "e1");
    expect(comp.target).toEqual({ kind: "existing", slug: "tea", rev: 7 });
    expect(comp.blocks.map((b) => b.id)).toEqual(["e1", "b1", "b2", "b3"]);
    expect(comp.blocks[0]).toMatchObject({ existing: true, text: "What I knew." });
  });

  it("reopening replaces the old body rather than stacking it", () => {
    const once = onExisting(sample(), NOTE, () => "e1");
    const twice = onExisting(once, { ...NOTE, rev: 8, body: "Newer." }, () => "e2");
    expect(twice.blocks.map((b) => b.id)).toEqual(["e2", "b1", "b2", "b3"]);
    expect(twice.target).toMatchObject({ rev: 8 });
  });

  it("an empty note adds no empty block", () => {
    expect(onExisting(emptyComposition(), { ...NOTE, body: " " }, ids()).blocks).toEqual(
      [],
    );
  });

  it("back to a new note drops the old note's text and title", () => {
    const comp = onNew(onExisting(sample(), NOTE, () => "e1"));
    expect(comp.target).toEqual({ kind: "new" });
    expect(comp.title).toBe("");
    expect(comp.blocks.map((b) => b.id)).toEqual(["b1", "b2", "b3"]);
  });
});

describe("saving", () => {
  it.each<[string, (c: Composition) => Composition, string | null]>([
    ["a complete note", (c) => c, null],
    ["no title", (c) => setTitle(c, "  "), "Give the note a title."],
    [
      "only blank text",
      (c) => ({ ...c, blocks: [{ id: "x", kind: "text", text: " ", draft: null }] }),
      "Add something to the note first.",
    ],
  ])("problem: %s", (_, change, expected) => {
    expect(problem(change(sample()))).toBe(expected);
  });

  it("images must be imported first", () => {
    const comp = sample();
    expect(pendingImages(comp).map((b) => b.id)).toEqual(["b3"]);
    expect(() => bodyOf(comp)).toThrow(/not been imported/);
  });

  it("writes the body block by block, images as directives", () => {
    const comp = withMedia(sample(), new Map([["b3", MEDIA]]));
    expect(pendingImages(comp)).toEqual([]);
    expect(bodyOf(comp)).toBe(
      `* Whisked. [[research-inbox/a]]\n\nMy own line.\n\n{{image:${MEDIA}|right|40|A bowl}}`,
    );
  });

  it.each<[string, Composition["target"], Record<string, unknown>]>([
    ["a new note", { kind: "new" }, {}],
    ["an update", { kind: "existing", slug: "tea", rev: 4 }, { note: "tea", rev: 4 }],
  ])("the request for %s", (_, target, extra) => {
    const comp = { ...withMedia(sample(), new Map([["b3", MEDIA]])), target };
    expect(noteRequest(comp)).toEqual({
      title: "Tea",
      body: bodyOf(comp),
      drafts: ["research-inbox/tea"],
      ...extra,
    });
  });

  it("names each draft the material came from once", () => {
    let comp = sample();
    comp = addText(comp, "More.", "bowls", () => "b9");
    expect(draftsOf(comp)).toEqual(["research-inbox/tea", "research-inbox/bowls"]);
  });
});
