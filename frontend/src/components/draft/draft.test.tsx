import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Job } from "../../api/types";
import { buildTopicTree } from "../../logic/topics";
import { draft as makeDraft, job, readyJob } from "../../test/fixtures";
import { renderWith } from "../../test/render";
import type { DraftActions } from "./actions";
import { ArticleView } from "./ArticleView";
import { DraftPane, type DraftPaneProps } from "./DraftPane";
import { FactsView } from "./FactsView";
import { ImagesView } from "./ImagesView";
import { PlanCard } from "./PlanCard";
import { SourcesView } from "./SourcesView";

function actions(
  inNote: string[] = [],
): DraftActions & { [K in keyof DraftActions]: ReturnType<typeof vi.fn> } {
  return {
    addText: vi.fn(),
    hasText: vi.fn((text: string) => inNote.includes(text)),
    addImage: vi.fn(),
    hasImage: vi.fn(() => false),
    digDeeper: vi.fn(),
    steer: vi.fn(),
    linkTo: vi.fn((target: string) => ({
      href: `/#/${target}`,
      ref: { db: "song", col: "x", id: target },
    })),
  } as never;
}

const BODY =
  "Tea was whisked [[research-inbox/a]].\n== Serving ==\n* In bowls [[sources/b]]\n* See [[characters/lin|Lin]]";

describe("ArticleView", () => {
  it("renders headings, paragraphs and list items, citations as chips", () => {
    renderWith(<ArticleView body={BODY} draft="tea" actions={actions()} />);
    expect(screen.getByRole("heading", { name: "Serving" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Lin" })).toHaveAttribute(
      "href",
      "/#/characters/lin",
    );
    expect(document.querySelectorAll(".st-cite")).toHaveLength(2);
  });

  it("adds a passage to the note as written, citations and all", async () => {
    const act = actions();
    renderWith(<ArticleView body={BODY} draft="tea" actions={act} />);
    const passage = screen
      .getByText(/Tea was whisked/)
      .closest(".st-passage") as HTMLElement;
    await userEvent.click(within(passage).getByRole("button", { name: /Add/ }));
    expect(act.addText).toHaveBeenCalledWith(
      "Tea was whisked [[research-inbox/a]].",
      "tea",
    );
  });

  it("marks a passage already in the note", () => {
    renderWith(
      <ArticleView
        body={BODY}
        draft="tea"
        actions={actions(["* In bowls [[sources/b]]"])}
      />,
    );
    const passage = screen.getByText(/In bowls/).closest(".st-passage") as HTMLElement;
    expect(passage).toHaveClass("is-added");
    expect(within(passage).getByRole("button", { name: /In note/ })).toBeDisabled();
  });

  it("digs deeper on the passage's words, without the markup", async () => {
    const act = actions();
    renderWith(<ArticleView body={BODY} draft="tea" actions={act} />);
    const passage = screen
      .getByText(/Tea was whisked/)
      .closest(".st-passage") as HTMLElement;
    await userEvent.click(within(passage).getByRole("button", { name: /Dig deeper/ }));
    expect(act.digDeeper).toHaveBeenCalledWith("Tea was whisked.");
  });

  it.each([
    ["Tea was whisked", ["research-inbox/a"]],
    ["In bowls", null],
  ])("offers to distrust only new sources (%s)", async (text, distrust) => {
    const act = actions();
    renderWith(<ArticleView body={BODY} draft="tea" actions={act} />);
    const passage = screen
      .getByText(new RegExp(text))
      .closest(".st-passage") as HTMLElement;
    const button = within(passage).queryByRole("button", { name: /Distrust/ });
    if (!distrust) return expect(button).toBeNull();
    await userEvent.click(button!);
    expect(act.steer).toHaveBeenCalledWith(distrust);
  });
});

describe("FactsView", () => {
  const source = readyJob("tea");
  const { facts, dropped_facts } = makeDraft(source);

  it("adds one fact, or all of them", async () => {
    const act = actions();
    renderWith(
      <FactsView facts={facts} dropped={dropped_facts} draft="tea" actions={act} />,
    );
    expect(screen.getByText("Supported")).toBeInTheDocument();
    expect(screen.getByText("Partly supported")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Add all/ }));
    expect(act.addText).toHaveBeenCalledTimes(2);
    expect(act.addText).toHaveBeenCalledWith(
      "* Tea was whisked into a froth. [[research-inbox/museum-tea]]",
      "tea",
    );
  });

  it("shows what didn't make it, and why, when asked", async () => {
    renderWith(
      <FactsView facts={facts} dropped={dropped_facts} draft="tea" actions={actions()} />,
    );
    expect(screen.queryByText("Tea came in bags.")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /What didn't make it \(1\)/ }),
    );
    expect(screen.getByText("Tea came in bags.")).toBeInTheDocument();
    expect(screen.getByText("The second check found it unsupported")).toBeInTheDocument();
  });
});

describe("SourcesView", () => {
  const facts = makeDraft(readyJob("tea")).facts;
  const source = (ref: string) => ({
    key: "s1",
    ref,
    url: "https://www.museum.example/tea",
    title: "Tea at the museum",
    new: true,
  });

  it.each<[string, string, boolean]>([
    ["a source still in the inbox can be distrusted", "research-inbox/museum-tea", true],
    ["a source already in the world cannot", "sources/museum-tea", false],
  ])("%s", (_, ref, distrustable) => {
    renderWith(<SourcesView sources={[source(ref)]} facts={facts} actions={actions()} />);
    expect(screen.queryByRole("button", { name: /Distrust/ }) !== null).toBe(distrustable);
    expect(screen.queryByText("In your sources") !== null).toBe(!distrustable);
  });

  it("shows each page's site, what was quoted from it, and distrusts it", async () => {
    const act = actions();
    renderWith(
      <SourcesView
        sources={[source("research-inbox/museum-tea")]}
        facts={facts}
        actions={act}
      />,
    );
    expect(screen.getByRole("link", { name: /Tea at the museum/ })).toHaveAttribute(
      "href",
      "https://www.museum.example/tea",
    );
    expect(screen.getByText(/museum\.example · 1 quote/)).toBeInTheDocument();
    expect(screen.getByText("“whisked until a white froth formed”")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Distrust/ }));
    expect(act.steer).toHaveBeenCalledWith(["research-inbox/museum-tea"]);
  });
});

describe("ImagesView", () => {
  const images = () => makeDraft(readyJob("tea")).images;

  it("adds a picture to the note with its preview", async () => {
    const act = actions();
    renderWith(
      <ImagesView
        images={images()}
        draft="tea"
        previewUrl={(i) => `/p/${i}`}
        actions={act}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Add to note/ }));
    expect(act.addImage).toHaveBeenCalledWith({
      draft: "tea",
      index: 0,
      caption: "A Jian bowl",
      previewUrl: "/p/0",
      mediaId: null,
    });
  });

  it("a picture whose preview fails is gone, and cannot be added", () => {
    const act = actions();
    renderWith(
      <ImagesView
        images={images()}
        draft="tea"
        previewUrl={(i) => `/p/${i}`}
        actions={act}
      />,
    );
    fireEvent.error(screen.getByRole("img", { name: "A Jian bowl" }));
    expect(screen.getByText(/no longer on the web/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Not available/ })).toBeDisabled();
  });
});

describe("PlanCard", () => {
  const waiting = job({
    state: "awaiting_approval",
    plan: {
      queries: [
        { q: "song tea", language: "en" },
        { q: "tea bowls", language: "en" },
      ],
      approved: false,
      expires_at: null,
    },
  });

  it("approves the searches as edited", async () => {
    const onApprove = vi.fn();
    renderWith(
      <PlanCard
        job={waiting}
        approving={false}
        cancelling={false}
        onApprove={onApprove}
        onCancel={() => {}}
      />,
    );
    await userEvent.clear(screen.getByLabelText("Search 1"));
    await userEvent.type(screen.getByLabelText("Search 1"), "song tea houses");
    await userEvent.click(screen.getByLabelText("Remove search 2"));
    await userEvent.click(screen.getByRole("button", { name: /Add a search/ }));
    await userEvent.click(screen.getByRole("button", { name: /Search with these/ }));
    expect(onApprove).toHaveBeenCalledWith([{ q: "song tea houses", language: "en" }]);
  });

  it("will not go on with no searches at all", async () => {
    renderWith(
      <PlanCard
        job={waiting}
        approving={false}
        cancelling={false}
        onApprove={() => {}}
        onCancel={() => {}}
      />,
    );
    await userEvent.click(screen.getByLabelText("Remove search 1"));
    await userEvent.click(screen.getByLabelText("Remove search 1"));
    expect(screen.getByText("Keep at least one search.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Search with these/ })).toBeDisabled();
  });
});

describe("DraftPane", () => {
  function props(
    jobs: Job[],
    selected: Job | null,
    extra: Partial<DraftPaneProps> = {},
  ): DraftPaneProps {
    const tree = buildTopicTree(jobs);
    const topic = selected
      ? (tree
          .flatMap(function all(n): typeof tree {
            return [n, ...n.children.flatMap(all)];
          })
          .find((n) => n.job.id === selected.id) ?? null)
      : null;
    const handler = () => vi.fn(async () => undefined);
    return {
      world: "song",
      topic,
      path: topic ? [topic] : [],
      draft: undefined,
      draftError: null,
      handlers: {
        cancel: handler(),
        approve: handler(),
        retry: handler(),
        digDeeper: handler(),
        steer: handler(),
        keep: handler(),
        close: handler(),
        discard: handler(),
      },
      pending: {
        cancel: false,
        approve: false,
        retry: false,
        digDeeper: false,
        steer: false,
        keep: false,
        close: false,
        discard: false,
      },
      errors: { retry: null, digDeeper: null, steer: null },
      onDialogClosed: vi.fn(),
      note: {
        addText: vi.fn(),
        hasText: () => false,
        addImage: vi.fn(),
        hasImage: () => false,
      },
      previewUrl: (slug, index) => `/p/${slug}/${index}`,
      linkTo: () => null,
      articleUrl: ({ id }) => `/#/${id}`,
      onSelect: vi.fn(),
      ...extra,
    };
  }

  it.each<[string, Partial<Job>, RegExp]>([
    [
      "researching",
      {
        state: "running",
        progress: { stage: "fetching", message: "Reading 2 of 8 sources" },
      },
      /Reading 2 of 8 sources/,
    ],
    [
      "failed",
      {
        state: "failed",
        error: { code: "no_sources", message: "Nothing usable was found." },
      },
      /Nothing usable was found/,
    ],
    [
      "saved",
      { state: "done", review: "done", notes: ["research/tea"] },
      /Saved to a note/,
    ],
    ["closed", { state: "done", review: "done" }, /This draft is closed/],
  ])("shows a %s topic", (_, fields, text) => {
    const shown = job(fields);
    renderWith(<DraftPane {...props([shown], shown)} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("invites a first question when nothing is open", () => {
    renderWith(<DraftPane {...props([], null)} />);
    expect(screen.getByText("Pick a topic, or ask a new question")).toBeInTheDocument();
  });

  it("stops a job being researched", async () => {
    const shown = job({ state: "running" });
    const p = props([shown], shown);
    renderWith(<DraftPane {...p} />);
    await userEvent.click(screen.getByRole("button", { name: /Stop researching/ }));
    expect(p.handlers.cancel).toHaveBeenCalledWith(shown);
  });

  it("asks a failed question again under the same parent", async () => {
    const shown = job({ state: "failed" });
    const p = props([shown], shown);
    renderWith(<DraftPane {...p} />);
    await userEvent.click(screen.getByRole("button", { name: /Ask again/ }));
    expect(p.handlers.retry).toHaveBeenCalledWith(shown);
  });

  it("reads a ready draft, digs deeper from it, and closes it", async () => {
    const ready = readyJob("tea", { question: "Song tea?" });
    const p = props([ready], ready, { draft: makeDraft(ready) });
    renderWith(<DraftPane {...p} />);
    expect(screen.getByRole("heading", { name: "Song Tea" })).toBeInTheDocument();
    expect(screen.getByText("Second-checked")).toBeInTheDocument();

    const passage = screen
      .getByText(/Tea was ground/)
      .closest(".st-passage") as HTMLElement;
    await userEvent.click(within(passage).getByRole("button", { name: /Dig deeper/ }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("Question for the sub-topic")).toHaveValue(
      "Tell me more about: Tea was ground to powder and whisked. (in the context of: Song tea?)",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: /Research/ }));
    expect(p.handlers.digDeeper).toHaveBeenCalledWith(
      expect.stringContaining("Tea was ground"),
      ready,
    );

    await userEvent.click(screen.getByRole("button", { name: /Done with it/ }));
    await userEvent.click(screen.getByRole("button", { name: /Close the draft/ }));
    expect(p.handlers.close).toHaveBeenCalledWith("tea");
  });

  describe("a steer waiting for its searches to be approved", () => {
    function waiting() {
      const ready = readyJob("tea");
      const steer = job({
        refines: "research-inbox/tea",
        state: "awaiting_approval",
        plan: {
          queries: [{ q: "jian ware", language: "en" }],
          approved: false,
          expires_at: null,
        },
      });
      const p = props([steer, ready], ready, { draft: makeDraft(ready) });
      renderWith(<DraftPane {...p} />);
      return { p, steer };
    }

    it("shows its plan over the draft, not an endless spinner", () => {
      waiting();
      expect(screen.getByText("Here's how I'll search again")).toBeInTheDocument();
      expect(screen.getByLabelText("Search 1")).toHaveValue("jian ware");
      expect(screen.queryByText(/Steering with your feedback/)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^Steer$/ })).toBeDisabled();
    });

    it.each<[string, "approve" | "cancel", (steer: Job) => unknown[]]>([
      [
        "Search with these",
        "approve",
        (steer) => [steer, [{ q: "jian ware", language: "en" }]],
      ],
      ["Cancel the steer", "cancel", (steer) => [steer]],
    ])("%s acts on the steer", async (button, handler, args) => {
      const { p, steer } = waiting();
      await userEvent.click(screen.getByRole("button", { name: button }));
      expect(p.handlers[handler]).toHaveBeenCalledWith(...args(steer));
    });
  });

  it("keeps a whole draft as a note, once asked", async () => {
    const ready = readyJob("tea");
    const p = props([ready], ready, { draft: makeDraft(ready) });
    renderWith(<DraftPane {...p} />);
    await userEvent.click(screen.getByRole("button", { name: /Keep as note/ }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/verified research note/)).toBeInTheDocument();
    expect(p.handlers.keep).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: /Keep as note/ }));
    expect(p.handlers.keep).toHaveBeenCalledWith("tea");
  });

  it("shows why asking a failed question again failed", () => {
    const shown = job({ state: "failed" });
    renderWith(
      <DraftPane
        {...props([shown], shown, {
          errors: { retry: "Too many jobs.", digDeeper: null, steer: null },
        })}
      />,
    );
    expect(screen.getByText("Too many jobs.")).toBeInTheDocument();
  });

  it("a closed dialog clears what its last attempt failed with", async () => {
    const ready = readyJob("tea");
    const p = props([ready], ready, { draft: makeDraft(ready) });
    renderWith(<DraftPane {...p} />);
    await userEvent.click(screen.getByRole("button", { name: /^Steer$/ }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }),
    );
    expect(p.onDialogClosed).toHaveBeenCalled();
  });

  it("steers a draft away from a distrusted source", async () => {
    const ready = readyJob("tea");
    const p = props([ready], ready, { draft: makeDraft(ready) });
    renderWith(<DraftPane {...p} />);
    await userEvent.click(screen.getByRole("button", { name: /^Steer$/ }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox"), "Ordinary drinkers, please.");
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /A tea blog/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: /Research again/ }));
    expect(p.handlers.steer).toHaveBeenCalledWith("tea", {
      feedback: "Ordinary drinkers, please.",
      exclude_sources: ["research-inbox/blog-tea"],
    });
  });
});
