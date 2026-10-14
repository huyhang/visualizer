// The assembled studio against the fake api: what a writer does, end to end,
// without a server.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { ApiError } from "../api/errors";
import type { ResearchApi } from "../api/ResearchApi";
import type { Availability, Job } from "../api/types";
import { emptyComposition, type Composition } from "../logic/compose";
import { fakeApi } from "../test/fakeApi";
import { draft, inboxRow, job, readyJob } from "../test/fixtures";
import { testQueryClient } from "../test/render";
import { render } from "@testing-library/react";
import type { CompositionStore } from "../hooks/useComposition";
import { blockedBy, type Blocked } from "./StudioNotice";

function memoryStore(
  initial: Composition | null = null,
): CompositionStore & { saved: Composition | null } {
  return {
    saved: initial,
    load() {
      return this.saved;
    },
    save(comp) {
      this.saved = comp;
    },
  };
}

function renderStudio(api: ResearchApi, store = memoryStore()) {
  let n = 0;
  render(
    <App
      api={api}
      store={store}
      newId={() => `id${++n}`}
      queryClient={testQueryClient()}
    />,
  );
  return store;
}

function setup() {
  const ready = readyJob("song-tea", { question: "How was tea served?" });
  const fake = fakeApi({
    jobs: [ready],
    inbox: [inboxRow("song-tea", ready.id, "Song Tea")],
    drafts: { "song-tea": draft(ready) },
    notes: [{ id: "tea", title: "Tea", rev: 3, updated: null }],
  });
  let n = 0;
  const store = memoryStore();
  render(
    <App
      api={fake.api}
      store={store}
      newId={() => `id${++n}`}
      queryClient={testQueryClient()}
    />,
  );
  return { ...fake, ready, store };
}

describe("Studio", () => {
  beforeEach(() => {
    window.location.hash = "";
  });

  it("lists topics and notes, and opens a draft", async () => {
    const { ready } = setup();
    await userEvent.click(await screen.findByRole("button", { name: /Song Tea/ }));
    expect(window.location.hash).toBe(`#topic=${ready.id}`);
    expect(await screen.findByRole("heading", { name: "Song Tea" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Tea/ })).toBeInTheDocument();
    expect(await screen.findByText(/Researcher · Ready/)).toBeInTheDocument();
  });

  it("asking selects the new topic and shows its progress", async () => {
    const { calls } = setup();
    await screen.findByText(/Researcher · Ready/);
    await userEvent.type(
      screen.getByLabelText("Research question"),
      "Tea houses in Kaifeng{Enter}",
    );
    expect(await screen.findByText(/Waiting for its turn/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "ask")!.args[0]).toMatchObject({
      question: "Tea houses in Kaifeng",
    });
  });

  it("collects from the draft into a note and saves it", async () => {
    const { calls, store } = setup();
    await userEvent.click(await screen.findByRole("button", { name: /Song Tea/ }));
    const passage = (await screen.findByText(/Tea was ground/)).closest(
      ".st-passage",
    ) as HTMLElement;
    await userEvent.click(within(passage).getByRole("button", { name: /Add/ }));
    expect(within(passage).getByRole("button", { name: /In note/ })).toBeDisabled();
    expect(store.saved!.blocks).toHaveLength(1);

    await userEvent.type(screen.getByLabelText("Note title"), "Powdered tea");
    await userEvent.click(screen.getByRole("button", { name: /Save note/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "saveNote")).toBe(true));
    expect(calls.find((c) => c.method === "saveNote")!.args[0]).toEqual({
      title: "Powdered tea",
      body: "Tea was ground to powder and whisked [[research-inbox/museum-tea]].",
      drafts: ["research-inbox/song-tea"],
    });
    expect(await screen.findByText(/Saved “Powdered tea”/)).toBeInTheDocument();
    // The composer now writes into the note it just saved.
    expect(await screen.findByRole("button", { name: /Update note/ })).toBeInTheDocument();
  });

  it("opening an existing note keeps what was collected", async () => {
    const { store } = setup();
    await userEvent.click(await screen.findByRole("button", { name: /Song Tea/ }));
    const passage = (await screen.findByText(/Tea was ground/)).closest(
      ".st-passage",
    ) as HTMLElement;
    await userEvent.click(within(passage).getByRole("button", { name: /Add/ }));
    const notesList = document.querySelector(".st-notes-list") as HTMLElement;
    await userEvent.click(within(notesList).getByRole("button", { name: /^Tea/ }));
    expect(await screen.findByText("What I knew.")).toBeInTheDocument();
    expect(store.saved!.target).toEqual({ kind: "existing", slug: "tea", rev: 3 });
    expect(store.saved!.blocks.map((b) => (b.kind === "text" ? b.text : b.kind))).toEqual([
      "What I knew.",
      "Tea was ground to powder and whisked [[research-inbox/museum-tea]].",
    ]);
  });

  it("keeps a whole draft as a note, and says where it went", async () => {
    const { calls } = setup();
    await userEvent.click(await screen.findByRole("button", { name: /Song Tea/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Keep as note/ }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: /Keep as note/ }),
    );
    expect(await screen.findByText("Kept as a research note")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "acceptDraft")!.args).toEqual(["song-tea"]);
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "/#/song/research/song-tea",
    );
  });

  it("one calm screen for a world whose research is not shared", async () => {
    const fake = fakeApi(
      {},
      {
        listJobs: () =>
          Promise.reject(
            new ApiError(403, "You do not have 'read' permission on this resource."),
          ),
      },
    );
    renderStudio(fake.api);
    expect(await screen.findByText("No research to show here")).toBeInTheDocument();
    expect(screen.queryByLabelText("Research question")).not.toBeInTheDocument();
    expect(screen.queryByText(/permission on this resource/)).not.toBeInTheDocument();
  });

  it("one calm screen when this stack has no GPU box", async () => {
    const fake = fakeApi(
      {},
      {
        availability: async () => ({
          state: "off" as const,
          can_submit: false,
          message: "No GPU box is configured for this stack.",
          model: null,
          verifier: null,
          private: true,
        }),
        listJobs: () => Promise.reject(new ApiError(503, "Research is off.")),
      },
    );
    renderStudio(fake.api);
    expect(await screen.findByText("Research is off")).toBeInTheDocument();
    expect(screen.queryByLabelText("Research question")).not.toBeInTheDocument();
  });

  it("a steer that replaced its draft leaves one topic, and the studio follows it", async () => {
    const original = readyJob("tea", { question: "Tea?" });
    const steer = job({
      refines: "research-inbox/tea",
      state: "running",
      question: "Tea?",
    });
    const settled: Job = {
      ...steer,
      state: "done",
      draft: "research-inbox/tea",
      review: "pending",
    };
    const superseded = {
      ...original,
      review: "superseded" as const,
      superseded_by: steer.id,
    };
    let lists = 0;
    const fake = fakeApi(
      { inbox: [inboxRow("tea", steer.id, "Song Tea")], drafts: { tea: draft(settled) } },
      {
        // The box finishes the steer; only a fresh list knows the original
        // was superseded by it.
        listJobs: async () => (++lists === 1 ? [steer, original] : [settled, superseded]),
        getJob: async () => settled,
      },
    );
    window.location.hash = `#topic=${original.id}`;
    renderStudio(fake.api);
    await waitFor(() => expect(window.location.hash).toBe(`#topic=${steer.id}`));
    expect(screen.getAllByRole("treeitem")).toHaveLength(1);
  });

  it("a steer cancelled at its plan leaves the draft free to steer again", async () => {
    const ready = readyJob("tea");
    const steer = job({
      refines: "research-inbox/tea",
      state: "awaiting_approval",
      plan: {
        queries: [{ q: "kilns", language: "en" }],
        approved: false,
        expires_at: null,
      },
    });
    let cancelled = false;
    const fake = fakeApi(
      { jobs: [steer, ready], inbox: [inboxRow("tea", ready.id, "Song Tea")] },
      {
        // The draft's own copy of the steer is a snapshot from when it was read.
        draft: async () => ({ ...draft(ready), refining: cancelled ? null : steer }),
        cancel: async () => {
          cancelled = true;
          return { ...steer, state: "cancelled" as const };
        },
      },
    );
    window.location.hash = `#topic=${ready.id}`;
    renderStudio(fake.api);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel the steer" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^Steer$/ })).toBeEnabled(),
    );
    expect(screen.queryByText(/Steering with your feedback/)).not.toBeInTheDocument();
  });

  it("a failed question shows in the ask box, not in Dig deeper", async () => {
    const ready = readyJob("song-tea", { question: "How was tea served?" });
    const fake = fakeApi(
      { jobs: [ready], drafts: { "song-tea": draft(ready) } },
      { ask: () => Promise.reject(new ApiError(429, "Too many research jobs.")) },
    );
    renderStudio(fake.api);
    await screen.findByText(/Researcher · Ready/);
    await userEvent.type(screen.getByLabelText("Research question"), "Kilns{Enter}");
    expect(await screen.findByText("Too many research jobs.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /How was tea served/ }));
    const passage = (await screen.findByText(/Tea was ground/)).closest(
      ".st-passage",
    ) as HTMLElement;
    await userEvent.click(within(passage).getByRole("button", { name: /Dig deeper/ }));
    expect(within(screen.getByRole("dialog")).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("what is added while a save imports its pictures stays in the composer", async () => {
    const ready = readyJob("song-tea");
    let finishImport: (media: { id: string }) => void = () => undefined;
    const fake = fakeApi(
      {
        jobs: [ready],
        inbox: [inboxRow("song-tea", ready.id, "Song Tea")],
        drafts: { "song-tea": draft(ready) },
      },
      { importImage: () => new Promise((resolve) => (finishImport = resolve)) },
    );
    const store = memoryStore();
    renderStudio(fake.api, store);
    await userEvent.click(await screen.findByRole("button", { name: /Song Tea/ }));
    await userEvent.click(await screen.findByRole("tab", { name: /Images/ }));
    await userEvent.click(screen.getByRole("button", { name: /Add to note/ }));
    await userEvent.type(screen.getByLabelText("Note title"), "Bowls");
    await userEvent.click(screen.getByRole("button", { name: /Save note/ }));

    // Mid-save: the picture is still importing when a passage is added.
    await userEvent.click(screen.getByRole("tab", { name: /Article/ }));
    const passage = screen
      .getByText(/Prized for their dark glaze/)
      .closest(".st-passage") as HTMLElement;
    await userEvent.click(within(passage).getByRole("button", { name: /Add/ }));
    finishImport({ id: "e".repeat(32) });

    expect(await screen.findByText(/Saved “Bowls”/)).toBeInTheDocument();
    await waitFor(() => expect(store.saved!.target.kind).toBe("existing"));
    const saved = fake.calls.find((c) => c.method === "saveNote")!.args[0] as {
      body: string;
    };
    expect(saved.body).not.toContain("Prized for their dark glaze");
    expect(
      store.saved!.blocks.some((b) => b.kind === "text" && b.text.includes("dark glaze")),
    ).toBe(true);
  });

  it("picks up a note left half-written in this browser", async () => {
    const ready = readyJob("x");
    const fake = fakeApi({ jobs: [ready] });
    const store = memoryStore({
      ...emptyComposition(),
      title: "Unfinished",
      blocks: [{ id: "a", kind: "text", text: "Half a thought.", draft: null }],
    });
    render(
      <App
        api={fake.api}
        store={store}
        newId={() => "z"}
        queryClient={testQueryClient()}
      />,
    );
    expect(await screen.findByDisplayValue("Unfinished")).toBeInTheDocument();
    expect(screen.getByText("Half a thought.")).toBeInTheDocument();
  });
});

describe("blockedBy", () => {
  const box = (state: Availability["state"]): Availability => ({
    state,
    can_submit: state === "ready",
    message: "",
    model: null,
    verifier: null,
    private: true,
  });

  it.each<[string, Availability | undefined, unknown, Blocked | null]>([
    ["research switched off", box("off"), null, "off"],
    ["off wins over a refusal", box("off"), new ApiError(403, "No."), "off"],
    ["a refusal", box("ready"), new ApiError(403, "No."), "no-access"],
    ["no such world", undefined, new ApiError(404, "No."), "no-access"],
    [
      "a sleeping box is not a block",
      box("unreachable"),
      new ApiError(503, "Asleep."),
      null,
    ],
    ["all well", box("ready"), null, null],
  ])("%s", (_, availability, error, expected) => {
    expect(blockedBy(availability, error)).toBe(expected);
  });
});
