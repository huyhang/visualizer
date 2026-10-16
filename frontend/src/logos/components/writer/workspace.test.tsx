import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { LogosApiError } from "../../api/errors";
import { memoryStore } from "../../logic/preferences";
import { memoryRecovery, recoveryKey } from "../../logic/recovery";
import { doc, para, text } from "../../test/docs";
import { AT, CHAPTER, doneReview, draftOf, reviewIssue } from "../../test/fakeApi";
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

describe("the title", () => {
  it("keeps a pasted title on one line, with the copy that sizes it in step", async () => {
    await opened();
    const user = userEvent.setup();
    const title = screen.getByRole("textbox", { name: "Section title" });
    const field = title.closest(".lw-title-field");
    await user.clear(title);
    expect(field).toHaveAttribute("data-value", title.getAttribute("placeholder"));
    await user.click(title);
    await user.paste("The Night\nthe Lights Went Out");
    expect(title).toHaveValue("The Night the Lights Went Out");
    expect(field).toHaveAttribute("data-value", "The Night the Lights Went Out");
  });

  it("never starts a second line on Enter", async () => {
    await opened();
    const user = userEvent.setup();
    const title = screen.getByRole("textbox", { name: "Section title" });
    await user.type(title, "{Enter}");
    expect(title).toHaveValue("The Gate");
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
    const done = screen.getByRole("list", { name: "Issues" });
    expect(within(done).getByText(/very very/)).toBeInTheDocument();
    // Its words are untouched: a set-aside issue is not "changed".
    expect(within(done).queryByText("Changed")).not.toBeInTheDocument();
  });

  it("puts an issue back, and says so, when the server refuses to set it aside", async () => {
    const { api, user } = await reviewed();
    vi.mocked(api.setIssueStatus).mockRejectedValueOnce(new LogosApiError(500, "No."));
    await user.click(screen.getByRole("button", { name: /very very/ }));
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(await screen.findByText("That did not save")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "All issues" }));
    expect(screen.getByText(/2 open/)).toBeInTheDocument();
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

  it("keeps asking for the editor's reply when one ask fails", async () => {
    const { api, clock, user } = await reviewed();
    vi.mocked(api.issue).mockRejectedValueOnce(new LogosApiError(503, "The box blinked."));
    await user.click(screen.getByRole("button", { name: /lifted the teapot/ }));
    await user.click(screen.getByRole("button", { name: "What would you do instead?" }));
    await act(async () => clock.runAll());
    expect(screen.queryByText("A kettle is right.")).not.toBeInTheDocument();
    await act(async () => clock.runAll());
    expect(await screen.findByText("A kettle is right.")).toBeInTheDocument();
  });

  it("keeps a message that could not be sent, with the error beside its own issue", async () => {
    const { api, user } = await reviewed();
    vi.mocked(api.discuss).mockRejectedValueOnce(
      new LogosApiError(429, "One reply at a time."),
    );
    await user.click(screen.getByRole("button", { name: /lifted the teapot/ }));
    await user.type(screen.getByRole("textbox", { name: "Reply to the editor" }), "Why?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("One reply at a time.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Reply to the editor" })).toHaveValue(
      "Why?",
    );
    await user.click(screen.getByRole("button", { name: "All issues" }));
    await user.click(screen.getByRole("button", { name: /very very/ }));
    expect(screen.queryByText("One reply at a time.")).not.toBeInTheDocument();
  });

  it("keeps every fix ready while the underlines are hidden, and shows the chosen issue's words", async () => {
    const { user } = await reviewed();
    await user.click(screen.getByRole("switch", { name: "Underline in the manuscript" }));
    expect(document.querySelectorAll(".logos-ann-editor")).toHaveLength(0);
    const list = screen.getByRole("list", { name: "Issues" });
    expect(within(list).getByText("Fix ready")).toBeInTheDocument();
    expect(within(list).queryByText("Changed")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /lifted the teapot/ }));
    expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(screen.queryByText("You changed this passage")).not.toBeInTheDocument();
    expect(document.querySelector(".logos-ann-editor")?.textContent).toBe(
      "lifted the teapot",
    );
  });

  it("takes J, K, A and D only from the issue list itself", async () => {
    const { api, user } = await reviewed();
    await user.click(screen.getByRole("button", { name: /lifted the teapot/ }));
    // A key pressed in the settings, which float outside the tab...
    await user.click(screen.getByRole("button", { name: "Review settings" }));
    (await screen.findByRole("combobox", { name: "Second check" })).focus();
    await user.keyboard("d");
    await user.keyboard("a");
    await user.keyboard("{Escape}");
    // ...or with Ctrl, as select-all is, does nothing to the issue.
    screen.getByRole("button", { name: "Accept" }).focus();
    await user.keyboard("{Control>}a{/Control}");
    expect(api.setIssueStatus).not.toHaveBeenCalled();
    expect(prose()).toContain("Lin lifted the teapot and poured.");
  });

  it("takes a fix back where it was made when its words come earlier too", async () => {
    const red = doc(para("p1", text("It was red. It was very red.")));
    const { user } = await reviewed({
      state: {
        drafts: [draftOf("draft-1", "Draft 1", red)],
        nextIssues: [reviewIssue("i1", { quote: "very red", replacement: "red" })],
      },
    });
    await user.click(screen.getByRole("button", { name: /very red/ }));
    await user.click(screen.getByRole("button", { name: "Accept" }));
    expect(prose()).toBe("It was red. It was red.");
    await user.click(within(toast()).getByRole("button", { name: "Undo" }));
    expect(prose()).toBe("It was red. It was very red.");
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

  it("keeps its fixes ready while its underlines are hidden", async () => {
    await opened({ state: { coach: [finding] } });
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /Coach/ }));
    await screen.findByText("Repeated word");
    await user.click(screen.getByRole("switch", { name: "Underline in the manuscript" }));
    expect(document.querySelectorAll(".logos-ann-coach")).toHaveLength(0);
    expect(screen.queryByText("You changed this passage")).not.toBeInTheDocument();
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

describe("reviews of other drafts", () => {
  const twoDrafts = {
    drafts: [draftOf("draft-1", "Draft 1"), draftOf("draft-2", "Brighter")],
    reviews: [doneReview("r1", "draft-1", [reviewIssue("i1")])],
  };

  it("opens a draft on its own reviews, not another draft's", async () => {
    await opened({ state: twoDrafts, route: { draft: "draft-2" } });
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Editor" }));
    expect(await screen.findByText("A second reader for this draft")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Issues" })).not.toBeInTheDocument();
    expect(document.querySelectorAll(".logos-ann-editor")).toHaveLength(0);
  });

  it("shows another draft's review when asked, read-only and not drawn on this one", async () => {
    await opened({ state: twoDrafts, route: { draft: "draft-2" } });
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Editor" }));
    await user.click(await screen.findByText(/Other reviews/));
    await user.click(screen.getByRole("button", { name: /Draft 1/ }));
    expect(await screen.findByText(/This review read “Draft 1”/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask the editor" })).toBeInTheDocument();
    expect(
      screen.queryByRole("switch", { name: "Underline in the manuscript" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /lifted the teapot/ }));
    expect(screen.getByText("Song tea was whisked in bowls.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument();
    expect(document.querySelectorAll(".logos-ann-editor")).toHaveLength(0);
  });
});
