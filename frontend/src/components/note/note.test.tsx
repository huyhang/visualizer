import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  addImage,
  addText,
  emptyComposition,
  setTitle,
  type Composition,
} from "../../logic/compose";
import { renderWith } from "../../test/render";
import { NotePane, type NotePaneProps } from "./NotePane";

function props(comp: Composition, extra: Partial<NotePaneProps> = {}): NotePaneProps {
  return {
    comp,
    notes: [{ id: "tea", title: "Tea", rev: 3, updated: null }],
    loadingNote: false,
    saving: false,
    saveError: null,
    linkTo: () => null,
    onTitle: vi.fn(),
    onNew: vi.fn(),
    onExisting: vi.fn(),
    onAddOwn: vi.fn(() => "own"),
    onChange: vi.fn(),
    onMove: vi.fn(),
    onRemove: vi.fn(),
    onClear: vi.fn(),
    onSave: vi.fn(),
    onReload: vi.fn(),
    ...extra,
  };
}

let n = 0;
const newId = () => `b${++n}`;
const filled = () =>
  addImage(
    addText(
      setTitle(emptyComposition(), "Song tea"),
      "Tea was whisked [[research-inbox/a]].",
      "tea",
      newId,
    ),
    { draft: "tea", index: 0, caption: "A bowl", previewUrl: "/p/0", mediaId: null },
    newId,
  );

describe("NotePane", () => {
  it("starts empty, with a hint, and cannot be saved", () => {
    renderWith(<NotePane {...props(emptyComposition())} />);
    expect(screen.getByText("Your note starts here")).toBeInTheDocument();
    expect(screen.getByText("Give the note a title.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save note/ })).toBeDisabled();
  });

  it("shows what was added and saves it", async () => {
    const p = props(filled());
    renderWith(<NotePane {...p} />);
    expect(screen.getByText(/Tea was whisked/)).toBeInTheDocument();
    expect(screen.getByAltText("A bowl")).toHaveAttribute("src", "/p/0");
    expect(screen.getByText("Imported when you save")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Save note/ }));
    expect(p.onSave).toHaveBeenCalled();
  });

  it.each([
    ["Move down", "onMove", [expect.any(String), 1]],
    ["Remove from note", "onRemove", [expect.any(String)]],
  ] as const)("%s", async (label, handler, args) => {
    const p = props(filled());
    renderWith(<NotePane {...p} />);
    await userEvent.click(screen.getAllByLabelText(label)[0]!);
    expect(p[handler]).toHaveBeenCalledWith(...args);
  });

  it("edits a block's wikitext on click", async () => {
    const p = props(filled());
    renderWith(<NotePane {...p} />);
    await userEvent.click(screen.getByText(/Tea was whisked/));
    const editor = screen.getByLabelText("Edit this block (wikitext)");
    expect(editor).toHaveValue("Tea was whisked [[research-inbox/a]].");
    await userEvent.type(editor, "!");
    expect(p.onChange).toHaveBeenLastCalledWith(expect.any(String), {
      text: "Tea was whisked [[research-inbox/a]].!",
    });
  });

  it("switches to an existing note from the picker", async () => {
    const p = props(filled());
    renderWith(<NotePane {...p} />);
    await userEvent.click(screen.getByRole("radio", { name: /Add to a note/ }));
    await userEvent.click(screen.getByRole("button", { name: "Tea" }));
    expect(p.onExisting).toHaveBeenCalledWith("tea");
  });

  it("says it will update an existing note", () => {
    const comp = {
      ...filled(),
      target: { kind: "existing" as const, slug: "tea", rev: 3 },
    };
    renderWith(<NotePane {...props(comp)} />);
    expect(screen.getByRole("button", { name: /Update note/ })).toBeEnabled();
    expect(screen.getByRole("radio", { name: /Song tea/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it.each([
    [true, "Load the latest version"],
    [false, null],
  ])(
    "a failed save (conflict: %s) says why and offers what helps",
    async (conflict, offer) => {
      const p = props(filled(), {
        saveError: { message: "This note was changed.", conflict },
      });
      renderWith(<NotePane {...p} />);
      expect(screen.getByRole("alert")).toHaveTextContent("This note was changed.");
      const button = screen.queryByRole("button", { name: "Load the latest version" });
      if (!offer) return expect(button).toBeNull();
      await userEvent.click(button!);
      expect(p.onReload).toHaveBeenCalled();
    },
  );
});
