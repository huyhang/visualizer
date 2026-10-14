import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AskRequest } from "../../api/types";
import { buildTopicTree } from "../../logic/topics";
import { job, readyJob } from "../../test/fixtures";
import { renderWith } from "../../test/render";
import { AskBox } from "./AskBox";
import { NotesList } from "./NotesList";
import { TopicTree } from "./TopicTree";

describe("TopicTree", () => {
  const root = readyJob("tea", { question: "Song tea?" });
  const child = job({ parent: root.id, state: "running", question: "Jian bowls?" });
  const tree = buildTopicTree([child, root]);

  it("shows each topic with its state, children under parents", () => {
    renderWith(<TopicTree nodes={tree} selectedId={child.id} onSelect={() => {}} />);
    const items = screen.getAllByRole("treeitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]!).getByRole("group")).toHaveTextContent("Jian bowls?");
    expect(screen.getByText(/Ready to read/)).toBeInTheDocument();
    expect(screen.getByText(/Researching/)).toBeInTheDocument();
    expect(items[1]).toHaveAttribute("aria-selected", "true");
  });

  it("selects a topic, and folds its children away", async () => {
    const onSelect = vi.fn();
    renderWith(<TopicTree nodes={tree} selectedId={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByTitle("Song tea?"));
    expect(onSelect).toHaveBeenCalledWith(root.id);
    await userEvent.click(screen.getByLabelText("Fold"));
    expect(screen.queryByText("Jian bowls?")).not.toBeInTheDocument();
  });
});

describe("AskBox", () => {
  function setup(props: Partial<Parameters<typeof AskBox>[0]> = {}) {
    const onAsk = vi.fn<(request: AskRequest) => Promise<unknown>>(async () => undefined);
    renderWith(
      <AskBox
        canSubmit
        unavailable={null}
        busy={false}
        error={null}
        onAsk={onAsk}
        {...props}
      />,
    );
    return { onAsk, input: screen.getByLabelText("Research question") };
  }

  it("asks on Enter and clears the box", async () => {
    const { onAsk, input } = setup();
    await userEvent.type(input, "How was tea served?{Enter}");
    expect(onAsk).toHaveBeenCalledWith(
      expect.objectContaining({ question: "How was tea served?", approve_plan: false }),
    );
    expect(input).toHaveValue("");
  });

  it("Shift+Enter breaks the line instead", async () => {
    const { onAsk, input } = setup();
    await userEvent.type(input, "Tea{Shift>}{Enter}{/Shift}more");
    expect(onAsk).not.toHaveBeenCalled();
    expect(input).toHaveValue("Tea\nmore");
  });

  it("asks to see the plan first when told to", async () => {
    const { onAsk, input } = setup();
    await userEvent.click(screen.getByLabelText("Research settings"));
    await userEvent.click(screen.getByText("Let me check the search plan first"));
    await userEvent.type(input, "Tea houses{Enter}");
    expect(onAsk).toHaveBeenCalledWith(expect.objectContaining({ approve_plan: true }));
  });

  it.each([
    [
      "the box cannot take it",
      { canSubmit: false, unavailable: "The GPU box is asleep." },
      "Tea houses",
    ],
    ["the question is too short", {}, "ab"],
  ])("will not ask when %s", async (_, props, question) => {
    const { onAsk, input } = setup(props);
    await userEvent.type(input, `${question}{Enter}`);
    expect(onAsk).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Research$/ })).toBeDisabled();
  });

  it("keeps the question when asking fails, and says why", async () => {
    const { input } = setup({
      error: "Too many jobs.",
      onAsk: async () => Promise.reject(new Error("busy")),
    });
    await userEvent.type(input, "Tea houses{Enter}");
    expect(input).toHaveValue("Tea houses");
    expect(screen.getByRole("alert")).toHaveTextContent("Too many jobs.");
  });
});

describe("NotesList", () => {
  it.each([
    [0, "No research notes yet. Save one from a draft."],
    [2, null],
  ])("with %i notes", (count, empty) => {
    const notes = Array.from({ length: count }, (_, n) => ({
      id: `n${n}`,
      title: `Note ${n}`,
      rev: 1,
      updated: null,
    }));
    renderWith(<NotesList notes={notes} activeSlug={null} onOpen={() => {}} />);
    if (empty) expect(screen.getByText(empty)).toBeInTheDocument();
    else expect(screen.getAllByRole("button")).toHaveLength(count);
  });

  it("filters a long list and opens a note", async () => {
    const onOpen = vi.fn();
    const notes = Array.from({ length: 8 }, (_, n) => ({
      id: `n${n}`,
      title: n === 3 ? "Lanterns" : `Note ${n}`,
      rev: 1,
      updated: null,
    }));
    renderWith(<NotesList notes={notes} activeSlug={null} onOpen={onOpen} />);
    await userEvent.type(screen.getByLabelText("Filter notes"), "lant");
    await userEvent.click(screen.getByRole("button", { name: /Lanterns/ }));
    expect(onOpen).toHaveBeenCalledWith("n3");
  });
});
