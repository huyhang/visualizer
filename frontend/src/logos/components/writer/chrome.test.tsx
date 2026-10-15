// The writing page's chrome: every action in one bar wears its own mark, since
// on a phone the mark is all of the button; and the Akasha tab tells "nothing
// matched" from "the lookup failed".

import type { UseQueryResult } from "@tanstack/react-query";
import { Editor } from "@tiptap/core";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { Entity } from "../../api/types";
import { logosToPm } from "../../doc/convert";
import { writerExtensions } from "../../editor/extensions";
import { CHAPTER } from "../../test/fakeApi";
import { AkashaTab } from "../tools/AkashaTab";
import { FormatBar } from "./FormatBar";
import { TopBar } from "./TopBar";

/** What each button draws: its icon's path, or its letter. */
const marks = (root: HTMLElement) =>
  [...root.querySelectorAll("button")].map(
    (button) => button.querySelector("path")?.getAttribute("d") ?? button.textContent,
  );

const noop = () => {};

describe("the writing page's bars", () => {
  it("never draws two top-bar actions the same way", () => {
    const { container } = render(
      <TopBar
        where="Volume One / The Gate"
        backHref="/contents"
        drafts={{
          rows: [
            { id: "a", name: "A", primary: true, rev: 1 },
            { id: "b", name: "B", primary: false, rev: 1 },
          ],
          current: { id: "b", name: "B", primary: false, rev: 1, document: CHAPTER },
          sectionRev: 1,
        }}
        words={12}
        status={{ state: "conflict" }}
        openDrawer={null}
        toolsCount={2}
        actions={{
          back: noop,
          switchDraft: noop,
          newDraft: noop,
          rename: noop,
          makePrimary: noop,
          compare: noop,
          preserve: noop,
          toggleOutline: noop,
          toggleTools: noop,
          done: noop,
        }}
      />,
    );
    const drawn = marks(container.querySelector("header")!);
    expect(drawn.length).toBeGreaterThanOrEqual(8);
    expect(new Set(drawn).size).toBe(drawn.length);
  });

  it("never draws two formatting tools the same way", () => {
    const editor = new Editor({
      element: document.createElement("div"),
      extensions: writerExtensions({
        makeId: () => "x",
        bridge: { onActivate: noop, onPlacement: noop },
        keys: { save: noop, lookUp: () => false },
      }),
      content: logosToPm(CHAPTER),
    });
    render(<FormatBar editor={editor} />);
    const drawn = marks(screen.getByRole("toolbar", { name: "Formatting" }));
    expect(drawn).toHaveLength(7);
    expect(new Set(drawn).size).toBe(7);
  });
});

describe("the Akasha tab", () => {
  const results = (patch: Partial<UseQueryResult<Entity[]>>) =>
    ({ isLoading: false, error: null, data: [], ...patch }) as UseQueryResult<Entity[]>;
  const subject = {
    kind: "lookup" as const,
    text: "Lin",
    range: { from: 1, to: 4 },
    linkable: true,
  };

  it.each<[string, Partial<UseQueryResult<Entity[]>>, string]>([
    ["nothing matched", { data: [] }, "No readable Akasha entity matched."],
    ["the lookup failed", { error: new Error("Akasha is down.") }, "Akasha is down."],
    ["it is still looking", { isLoading: true }, "Searching Akasha…"],
  ])("says when %s", (_name, patch, message) => {
    render(
      <AkashaTab
        subject={subject}
        results={results(patch)}
        onLink={vi.fn()}
        onOpen={vi.fn()}
        onUnlink={vi.fn()}
      />,
    );
    expect(screen.getByText(message)).toBeInTheDocument();
  });

  it("offers to link only words within one paragraph", () => {
    const entity = {
      database: "ember",
      collection: "characters",
      id: "lin",
      title: "Lin Qingyu",
      database_title: "Ember",
      collection_title: "Characters",
    };
    render(
      <AkashaTab
        subject={{ ...subject, linkable: false }}
        results={results({ data: [entity] })}
        onLink={vi.fn()}
        onOpen={vi.fn()}
        onUnlink={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Link mention" })).toBeDisabled();
  });
});
