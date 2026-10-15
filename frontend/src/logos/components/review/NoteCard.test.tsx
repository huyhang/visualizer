import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { ReviewIssue } from "../../api/types";
import { coachNote, editorNote, type Note, type NoteActions } from "../../logic/notes";
import { reviewIssue } from "../../test/fakeApi";
import { NoteCard } from "./NoteCard";

const actions = (): NoteActions => ({
  accept: vi.fn(),
  editHere: vi.fn(),
  dismiss: vi.fn(),
  resolve: vi.fn(),
  reopen: vi.fn(),
  discuss: vi.fn(),
  ignoreRule: vi.fn(),
  show: vi.fn(),
  openReference: vi.fn(),
});

const editor = (patch: Partial<ReviewIssue> = {}) =>
  editorNote(reviewIssue("i1", patch), "r1");
const coach = (replacement: string | null) =>
  coachNote({
    id: "c1",
    block: "p1",
    category: "flow",
    title: "Adverb",
    message: "Cut it.",
    excerpt: "very",
    replacement,
  });

const buttons = () =>
  screen
    .queryAllByRole("button")
    .map((button) => button.getAttribute("aria-label") ?? button.textContent);

describe("NoteCard", () => {
  it.each<[string, Note, boolean, "popover" | "detail", string[]]>([
    ["a fix, in the prose", editor(), true, "popover", ["Accept", "Dismiss", "Discuss"]],
    [
      "advice only",
      editor({ replacement: null }),
      true,
      "popover",
      ["Edit here", "Dismiss", "Discuss"],
    ],
    ["words since rewritten", editor(), false, "detail", ["Mark resolved", "Dismiss"]],
    ["dismissed", editor({ status: "dismissed" }), true, "detail", ["Reopen"]],
    ["a Coach fix", coach("really"), true, "popover", ["Accept", "Dismiss", "Ignore rule"]],
    [
      "a Coach note without a fix",
      coach(null),
      true,
      "popover",
      ["Edit here", "Dismiss", "Ignore rule"],
    ],
  ])("%s offers the right actions", (_name, note, placed, variant, expected) => {
    render(<NoteCard note={note} actions={actions()} placed={placed} variant={variant} />);
    const offered = buttons().filter(
      (label) => !/Based on|Show in the manuscript/.test(label ?? ""),
    );
    expect(offered).toEqual(expected);
  });

  it("shows what a fix changes, struck through and added", () => {
    render(<NoteCard note={editor()} actions={actions()} placed variant="popover" />);
    expect(
      screen.getByLabelText("Replace “lifted the teapot” with “whisked the tea”"),
    ).toBeInTheDocument();
    expect(document.querySelector("del")?.textContent).toBe("lifted the teapot");
    expect(document.querySelector("ins")?.textContent).toBe("whisked the tea");
  });

  it("names the article an issue is based on and opens it", async () => {
    const spies = actions();
    render(
      <NoteCard
        note={editor()}
        actions={spies}
        placed
        variant="popover"
        references={[{ ref: "ember/research/tea", kind: "research", title: "Song tea" }]}
      />,
    );
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: /Based on Song tea/ }));
    expect(spies.openReference).toHaveBeenCalledWith("ember/research/tea");
  });

  it.each<[Partial<ReviewIssue>, string]>([
    [{ verified: true }, "Second-checked"],
    [{ dismissed_before: "r0" }, "Dismissed before"],
    [
      {
        discussion: [
          {
            role: "editor",
            text: "No.",
            at: null,
            stance: "maintains",
            suggestion: null,
            replacement: null,
            model: null,
          },
        ],
      },
      "Editor maintains",
    ],
  ])("says when an issue is %j", (patch, badge) => {
    render(<NoteCard note={editor(patch)} actions={actions()} placed variant="detail" />);
    expect(screen.getByText(badge)).toBeInTheDocument();
  });
});
