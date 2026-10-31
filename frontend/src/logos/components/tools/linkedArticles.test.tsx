// Linking an article to the chapter from a lookup: the article is listed in
// the Akasha tab, and the words looked up are left exactly as they were.

import type { Editor } from "@tiptap/core";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Entity } from "../../api/types";
import { AT } from "../../test/fakeApi";
import { renderWriter } from "../../test/renderWriter";

const LIN: Entity = {
  database: "ember",
  collection: "characters",
  id: "lin",
  title: "Lin Qingyu",
  database_title: "Ember",
  collection_title: "Characters",
};
const LIN_REF = { database: "ember", collection: "characters", id: "lin" };
const TEA = { database: "ember", collection: "research", id: "tea" };
const SONG_TEA = {
  ...TEA,
  database_title: "Ember",
  collection_title: "Research",
  title: "Song tea",
  fields: [{ name: "Body", value: "Tea was powdered and whisked." }],
  missing: false,
};

/** The writing tools beside the page; the scene cards above it are articles too. */
const tools = () => within(screen.getByRole("complementary", { name: "Writing tools" }));

async function opened(setup: Parameters<typeof renderWriter>[0] = {}) {
  const view = renderWriter(setup);
  await screen.findByRole("textbox", { name: "Edit The Gate" });
  const editor = (document.querySelector(".ProseMirror") as unknown as { editor: Editor })
    .editor;
  return { ...view, editor, user: userEvent.setup() };
}

/** Select `words` in the prose and look them up, as ⌘K does. */
async function lookUp(editor: Editor, words: string) {
  let from = -1;
  editor.state.doc.descendants((node, pos) => {
    const at = node.isText ? (node.text ?? "").indexOf(words) : -1;
    if (from < 0 && at >= 0) from = pos + at;
  });
  act(() => {
    editor.commands.setTextSelection({ from, to: from + words.length });
    editor.commands.keyboardShortcut("Mod-k");
  });
  return screen.findByText(`Selected: “${words}”`);
}

describe("linking an article to the chapter", () => {
  it("lists the article beside the chapter and leaves the words alone", async () => {
    const { editor, user, api } = await opened({ state: { entities: [LIN] } });
    const before = editor.getJSON();

    await lookUp(editor, "Lin");
    await user.click(await screen.findByRole("button", { name: "Link to chapter" }));

    expect(api.updateSectionArticles).toHaveBeenCalledWith(AT, [LIN_REF], 5);
    const list = screen.getByRole("region", { name: "Linked to this chapter" });
    expect(await within(list).findByText("Lin Qingyu")).toBeInTheDocument();
    expect(
      screen.getByText("Linked to this chapter", { selector: "span" }),
    ).toBeInTheDocument();
    expect(editor.getJSON()).toEqual(before);
    expect(document.querySelector(".entity-mention")).toBeNull();
  });

  it("adds to what is already linked, and takes one off", async () => {
    const { editor, user, api } = await opened({
      state: {
        entities: [LIN],
        linked: [SONG_TEA],
      },
    });
    const list = await screen.findByRole("region", { name: "Linked to this chapter" });
    expect(await within(list).findByText("Song tea")).toBeInTheDocument();

    await lookUp(editor, "Lin");
    await user.click(await screen.findByRole("button", { name: "Link to chapter" }));
    expect(api.updateSectionArticles).toHaveBeenLastCalledWith(AT, [TEA, LIN_REF], 5);

    await user.click(
      within(screen.getByRole("region", { name: "Linked to this chapter" })).getByRole(
        "button",
        { name: "Unlink Song tea" },
      ),
    );
    expect(api.updateSectionArticles).toHaveBeenLastCalledWith(AT, [LIN_REF], 6);
    await waitFor(() =>
      expect(
        screen.getByRole("region", { name: "Linked to this chapter" }),
      ).not.toHaveTextContent("Song tea"),
    );
    expect(await screen.findByText("Song tea is no longer linked")).toBeInTheDocument();
  });

  it("previews a linked article in the tab when its name is clicked", async () => {
    const { user } = await opened({ state: { linked: [SONG_TEA] } });
    const list = await screen.findByRole("region", { name: "Linked to this chapter" });

    await user.click(await within(list).findByRole("button", { name: /^Song tea/ }));

    const card = tools().getByRole("article");
    expect(card).toHaveTextContent("Song tea");
    expect(card).toHaveTextContent("Tea was powdered and whisked.");
    await user.click(within(card).getByRole("button", { name: "Unlink from chapter" }));
    await waitFor(() => expect(tools().queryByRole("article")).toBeNull());
  });

  it("says so when the link could not be saved, and lists nothing new", async () => {
    const { editor, user, state } = await opened({ state: { entities: [LIN] } });
    state.sectionRev = 99; // another tab moved the section on

    await lookUp(editor, "Lin");
    await user.click(await screen.findByRole("button", { name: "Link to chapter" }));

    expect(await screen.findByText("That did not work")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Linked to this chapter" }),
    ).not.toHaveTextContent("Lin Qingyu");
  });
});
