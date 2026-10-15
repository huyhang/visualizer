import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { memoryStore } from "../../logic/preferences";
import { memoryRecovery, recoveryKey } from "../../logic/recovery";
import { doc, para, text } from "../../test/docs";
import { AT, CHAPTER, reviewIssue } from "../../test/fakeApi";
import { renderWriter } from "../../test/renderWriter";

const prose = () => document.querySelector(".lw-editor")?.textContent ?? "";
const saveStatus = () => document.querySelector(".lw-save")?.textContent ?? "";
const toast = () => document.querySelector<HTMLElement>(".st-toast")!;

async function opened(setup: Parameters<typeof renderWriter>[0] = {}) {
  const view = renderWriter(setup);
  await screen.findByRole("textbox", { name: "Edit The Gate" });
  return view;
}

async function reviewed(setup: Parameters<typeof renderWriter>[0] = {}) {
  const view = await opened(setup);
  const user = userEvent.setup();
  await user.click(screen.getByRole("tab", { name: "Editor" }));
  await user.click(await screen.findByRole("button", { name: "Ask the editor" }));
  await screen.findByRole("list", { name: "Issues" });
  return { ...view, user };
}

describe("opening a draft", () => {
  it("shows the title, the prose, the word count and that it is saved", async () => {
    await opened();
    expect(screen.getByRole("textbox", { name: "Section title" })).toHaveValue("The Gate");
    expect(prose()).toContain("Lin lifted the teapot and poured.");
    expect(screen.getByText("12 words")).toBeInTheDocument();
    expect(saveStatus()).toBe("Saved");
  });

  it("sends a reader who may not write to the passage in the reader", async () => {
    const { deps } = renderWriter({
      state: {
        manuscript: {
          ...(await import("../../test/fakeApi")).fakeState().manuscript,
          permissions: { read: true, write: false },
        },
      },
      route: { block: "p2" },
    });
    await waitFor(() => expect(deps.navigate).toHaveBeenCalledWith("/read/one/gate#p2"));
  });

  it("says so when the section has gone", async () => {
    renderWriter({ route: { section: "nowhere" } });
    expect(await screen.findByText("This draft could not be opened")).toBeInTheDocument();
    expect(screen.getByText(/not in the manuscript any more/)).toBeInTheDocument();
  });
});

describe("saving", () => {
  it("saves a new title once typing pauses, draft first and then the section", async () => {
    const { api, clock } = await opened();
    const user = userEvent.setup();
    const title = screen.getByRole("textbox", { name: "Section title" });
    await user.clear(title);
    await user.type(title, "The Broken Gate");
    expect(saveStatus()).toBe("Saved on this device");
    await act(async () => clock.runAll());
    await waitFor(() =>
      expect(api.updateSectionTitle).toHaveBeenCalledWith(AT, "The Broken Gate", 5),
    );
    expect(api.saveDraft).toHaveBeenCalledWith(
      AT,
      "draft-1",
      expect.objectContaining({ name: "Draft 1" }),
      3,
      false,
    );
    await waitFor(() => expect(saveStatus()).toBe("Saved"));
  });

  it("holds a save another tab beat as a conflict, and preserves it as a new draft", async () => {
    const { api, clock, deps, state } = await opened({ state: { failSaves: 409 } });
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Section title" }), "!");
    await act(async () => clock.runAll());
    expect(await screen.findByText("Conflict preserved")).toBeInTheDocument();
    state.failSaves = null; // a new draft has no one to race
    await user.click(screen.getByRole("button", { name: "Preserve as new draft" }));
    await waitFor(() =>
      expect(deps.navigate).toHaveBeenCalledWith("/write/one/gate?draft=draft-2"),
    );
    expect(api.createDraft).toHaveBeenCalledWith(
      AT,
      expect.stringMatching(/^Recovered /),
      "draft-1",
    );
  });

  it.each<[string, number, string]>([
    [
      "typed over the draft the server has: they carry on saving",
      3,
      "Saved on this device",
    ],
    ["typed over an older revision: they are held as a conflict", 2, "Conflict preserved"],
  ])("finds words this device kept, %s", async (_name, draftRev, status) => {
    const kept = doc(para("p1", text("Words from before the crash.")));
    const recovery = memoryRecovery({
      [recoveryKey({ user: "mara", ...AT, draft: "draft-1" })]: {
        document: kept,
        name: "Draft 1",
        title: "The Gate",
        draftRev,
        caret: { block: "p1", offset: 5 },
        savedAt: "earlier",
      },
    });
    await opened({ recovery });
    expect(prose()).toContain("Words from before the crash.");
    expect(saveStatus()).toBe(status);
  });
});

describe("the editor's review", () => {
  it("asks for a review of the saved draft and lists what came back, in reading order", async () => {
    const { api } = await reviewed();
    expect(api.askForReview).toHaveBeenCalledWith(AT, {
      draft: "draft-1",
      checks: ["continuity", "anachronism", "prose"],
      verify: "auto",
      dialect: "en-US",
      include: [],
    });
    const rows = within(screen.getByRole("list", { name: "Issues" })).getAllByRole(
      "button",
    );
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("lifted the teapot"),
      expect.stringContaining("very very"),
    ]);
    expect(screen.getByText(/2 open/)).toBeInTheDocument();
  });

  it("underlines each open issue's words in the prose", async () => {
    await reviewed();
    const underlined = [...document.querySelectorAll<HTMLElement>(".logos-ann-editor")].map(
      (el) => el.textContent,
    );
    expect(underlined).toEqual(["lifted the teapot", "very very"]);
  });

  it("accepts a fix: the words change, the issue is resolved, and Undo puts both back", async () => {
    const { api, user } = await reviewed();
    await user.click(screen.getByRole("button", { name: /lifted the teapot/ }));
    await user.click(screen.getByRole("button", { name: "Accept" }));
    expect(prose()).toContain("Lin whisked the tea and poured.");
    await waitFor(() =>
      expect(api.setIssueStatus).toHaveBeenCalledWith(AT, "r1", "i1", "resolved"),
    );
    await screen.findByText("Fix applied");
    await user.click(within(toast()).getByRole("button", { name: "Undo" }));
    expect(prose()).toContain("Lin lifted the teapot and poured.");
    await waitFor(() =>
      expect(api.setIssueStatus).toHaveBeenLastCalledWith(AT, "r1", "i1", "open"),
    );
  });

  it("offers to edit by hand when the editor gave advice rather than words", async () => {
    const { user } = await reviewed();
    await user.click(screen.getByRole("button", { name: /very very/ }));
    expect(screen.getByRole("button", { name: "Edit here" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
  });

  it("dismisses an issue, which moves it to Done", async () => {
    const { api, user } = await reviewed();
    await user.click(screen.getByRole("button", { name: /very very/ }));
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() =>
      expect(api.setIssueStatus).toHaveBeenCalledWith(AT, "r1", "i2", "dismissed"),
    );
    await user.click(screen.getByRole("button", { name: "All issues" }));
    await user.click(screen.getByRole("button", { name: "Done 1" }));
    expect(
      within(screen.getByRole("list", { name: "Issues" })).getByText(/very very/),
    ).toBeInTheDocument();
  });

  it("talks an issue over: the editor's revised fix becomes the one to accept", async () => {
    const { api, clock, user } = await reviewed();
    await user.click(screen.getByRole("button", { name: /lifted the teapot/ }));
    await user.click(screen.getByRole("button", { name: "What would you do instead?" }));
    expect(api.discuss).toHaveBeenCalledWith(AT, "r1", "i1", "What would you do instead?");
    await act(async () => clock.runAll());
    expect(await screen.findByText("A kettle is right.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Accept" }));
    expect(prose()).toContain("Lin lifted the kettle and poured.");
  });

  it("steps through issues with J and K", async () => {
    const { user } = await reviewed();
    const list = screen.getByRole("list", { name: "Issues" });
    within(list).getAllByRole("button")[0]!.focus();
    await user.keyboard("j");
    expect(screen.getByText("Song tea was whisked in bowls.")).toBeInTheDocument();
  });

  it("says why the editor cannot be asked", async () => {
    await opened({
      state: {
        availability: {
          state: "off",
          can_submit: false,
          message: "No GPU box is configured for this stack.",
          model: null,
          verifier: null,
          private: true,
        },
      },
    });
    await userEvent.setup().click(screen.getByRole("tab", { name: "Editor" }));
    expect(
      await screen.findByText("No GPU box is configured for this stack."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask the editor" })).toBeDisabled();
  });

  it("shows an issue whose words were since rewritten as changed, and offers to resolve it", async () => {
    const { user } = await reviewed({
      state: { nextIssues: [reviewIssue("i1", { quote: "words no longer there" })] },
    });
    await user.click(screen.getByRole("button", { name: /words no longer there/ }));
    expect(screen.getByText("You changed this passage")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark resolved" })).toBeInTheDocument();
  });
});

describe("the Writing Coach", () => {
  const finding = {
    id: "p2:flow:Repeated word:very very",
    block: "p2",
    category: "flow",
    title: "Repeated word",
    message: "The same word twice.",
    excerpt: "very very",
    replacement: "very",
  };

  it("lists its findings, underlines them, and accepts one", async () => {
    await opened({ state: { coach: [finding] } });
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /Coach/ }));
    expect(await screen.findByText("Repeated word")).toBeInTheDocument();
    expect(document.querySelector(".logos-ann-coach")?.textContent).toBe("very very");
    await user.click(screen.getByRole("button", { name: "Accept" }));
    expect(prose()).toContain("The gate was very old.");
  });

  it("remembers a rule the writer ignores, for this page and the Review page", async () => {
    const store = memoryStore();
    await opened({ state: { coach: [finding] }, store });
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /Coach/ }));
    await user.click(await screen.findByRole("button", { name: "Ignore rule" }));
    expect(store.getItem("logos-writing-ignored:mara")).toBe('["Repeated word"]');
    expect(screen.getByText("No local suggestions. Keep writing.")).toBeInTheDocument();
  });

  it("reads the draft in the dialect the writer chose", async () => {
    const { api } = await opened({
      store: memoryStore({ "logos-writing-dialect:mara": "en-GB" }),
    });
    await waitFor(() => expect(api.coach).toHaveBeenCalledWith("ember", CHAPTER, "en-GB"));
  });
});
