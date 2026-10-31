// The writing page's chrome: every action in one bar wears its own mark, since
// on a phone the mark is all of the button; and the Akasha tab tells "nothing
// matched" from "the lookup failed".

import type { UseQueryResult } from "@tanstack/react-query";
import { Editor } from "@tiptap/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { Entity, LinkedArticle } from "../../api/types";
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
  const linked = (patch: Partial<UseQueryResult<LinkedArticle[]>> = {}) =>
    ({ isLoading: false, error: null, data: [], ...patch }) as UseQueryResult<
      LinkedArticle[]
    >;
  const subject = { kind: "lookup" as const, text: "Lin" };
  const entity: Entity = {
    database: "ember",
    collection: "characters",
    id: "lin",
    title: "Lin Qingyu",
    database_title: "Ember",
    collection_title: "Characters",
  };
  const tab = (patch: Partial<Parameters<typeof AkashaTab>[0]> = {}) =>
    render(
      <AkashaTab
        subject={subject}
        results={results({})}
        linked={linked()}
        where="chapter"
        busy={false}
        onLink={vi.fn()}
        onUnlinkArticle={vi.fn()}
        onOpen={vi.fn()}
        onUnlink={vi.fn()}
        {...patch}
      />,
    );

  it.each<[string, Partial<UseQueryResult<Entity[]>>, string]>([
    ["nothing matched", { data: [] }, "No readable Akasha entity matched."],
    ["the lookup failed", { error: new Error("Akasha is down.") }, "Akasha is down."],
    ["it is still looking", { isLoading: true }, "Searching Akasha…"],
  ])("says when %s", (_name, patch, message) => {
    tab({ results: results(patch) });
    expect(screen.getByText(message)).toBeInTheDocument();
  });

  it("offers to link a match to the chapter, or says it already is", () => {
    const onLink = vi.fn();
    const { unmount } = tab({ results: results({ data: [entity] }), onLink });
    fireEvent.click(screen.getByRole("button", { name: "Link to chapter" }));
    expect(onLink).toHaveBeenCalledWith(entity);
    unmount();

    tab({
      results: results({ data: [entity] }),
      linked: linked({ data: [{ ...entity, title: "Lin Qingyu", missing: false }] }),
    });
    expect(screen.queryByRole("button", { name: "Link to chapter" })).toBeNull();
    expect(
      screen.getByText("Linked to this chapter", { selector: "span" }),
    ).toBeInTheDocument();
  });

  it("lists what is linked, even one it cannot open or that is gone", () => {
    const onUnlinkArticle = vi.fn();
    const gone = {
      database: "ember",
      collection: "places",
      id: "old-mill",
      title: null,
      missing: true,
    };
    tab({
      subject: { kind: "idle" },
      linked: linked({
        data: [
          { ...entity, title: "Lin Qingyu", missing: false },
          {
            database: "ember",
            collection: "secrets",
            id: "x",
            title: null,
            missing: false,
          },
          gone,
        ],
      }),
      onUnlinkArticle,
    });

    const list = screen.getByRole("region", { name: "Linked to this chapter" });
    expect(list).toHaveTextContent("Lin Qingyu");
    expect(list).toHaveTextContent("An article you can't open");
    expect(list).toHaveTextContent("No longer in Akasha");
    expect(
      screen.getByRole("button", { name: "Open Lin Qingyu in Akasha" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open old-mill in Akasha" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Unlink old-mill" }));
    expect(onUnlinkArticle).toHaveBeenCalledWith(gone);
  });

  it("says when nothing is linked yet", () => {
    tab({ subject: { kind: "idle" } });
    expect(screen.getByText(/Nothing yet\./)).toBeInTheDocument();
  });
});
