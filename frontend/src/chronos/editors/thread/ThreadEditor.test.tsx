import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PlotlinePreview } from "../../api/types";
import { fakeApi, type FakeApi } from "../../test/fakeApi";
import { goalRef, summary } from "../../test/fixtures";
import { renderWorkspace } from "../../test/renderChronos";
import { historyKey } from "./useThreadDraft";

const ORDER = ["departs", "exchange", "coronation"];

/** The fixture book, with the knight's road owning all three of its scenes. */
function bookApi(): FakeApi {
  const api = fakeApi();
  const road = api.plotlines.get("road");
  if (road) api.plotlines.set("road", { ...road, events: [...ORDER] });
  return api;
}

/** A preview that finds two problems whenever the knight sets out first. */
function judging(api: FakeApi) {
  api.previewPlotline = vi.fn(async (_book, candidate) => {
    const departsFirst = candidate.events[0] === "departs";
    const preview: PlotlinePreview = {
      kind: "plotline-preview",
      id: candidate.id ?? "",
      events: candidate.events,
      goals: candidate.goals ?? [],
      goal_refs: (candidate.goals ?? []).map(goalRef),
      effective_events: candidate.events.map((e: string) => summary(e)),
      status: { conflicts: departsFirst ? 2 : 0, ends_at_terminus: { state: "ok" } },
    };
    return preview;
  });
}

async function openEditor(api: FakeApi = bookApi()) {
  const harness = renderWorkspace("#/ember-pact/road", api);
  await userEvent.click(await screen.findByRole("button", { name: "Edit thread" }));
  const dialog = await screen.findByRole("dialog", { name: "Edit thread" });
  await within(dialog).findByRole("list", { name: "Scenes" });
  return { ...harness, dialog };
}

const lastPreviewOrder = (api: FakeApi) => {
  const calls = api.callsTo("previewPlotline");
  return (calls[calls.length - 1]?.[1] as { events: string[] } | undefined)?.events;
};

const row = (dialog: HTMLElement, list: string, name: RegExp) =>
  within(within(dialog).getByRole("list", { name: list })).getByRole("listitem", {
    name: name,
  });

describe("the thread editor", () => {
  it("asks the server about the order after a keyboard move", async () => {
    const { api, dialog } = await openEditor();
    await waitFor(() => expect(lastPreviewOrder(api)).toEqual(ORDER));
    fireEvent.keyDown(row(dialog, "Scenes", /^Aldric Departs/), { key: "ArrowDown" });
    await waitFor(() =>
      expect(lastPreviewOrder(api)).toEqual(["exchange", "departs", "coronation"]),
    );
  });

  it("does not ask the server again for a new name", async () => {
    const { api, dialog } = await openEditor();
    await waitFor(() => expect(lastPreviewOrder(api)).toEqual(ORDER));
    const asked = api.callsTo("previewPlotline").length;
    await userEvent.type(within(dialog).getByLabelText("Name"), " Revised");
    await new Promise((r) => setTimeout(r, 400));
    expect(api.callsTo("previewPlotline")).toHaveLength(asked);
  });

  it("moves with Alt held as well, and takes a scene out with Delete", async () => {
    const { api, dialog } = await openEditor();
    await waitFor(() => expect(lastPreviewOrder(api)).toEqual(ORDER));
    fireEvent.keyDown(row(dialog, "Scenes", /^The Coronation/), {
      key: "ArrowUp",
      altKey: true,
    });
    await waitFor(() =>
      expect(lastPreviewOrder(api)).toEqual(["departs", "coronation", "exchange"]),
    );
    fireEvent.keyDown(row(dialog, "Scenes", /^Aldric Departs/), { key: "Delete" });
    await waitFor(() => expect(lastPreviewOrder(api)).toEqual(["coronation", "exchange"]));
  });

  it("undoes and redoes a move, from the toolbar and the keyboard", async () => {
    const { api, dialog } = await openEditor();
    await waitFor(() => expect(lastPreviewOrder(api)).toEqual(ORDER));
    const undo = within(dialog).getByRole("button", { name: /^Undo/ });
    expect(undo).toBeDisabled();
    fireEvent.keyDown(row(dialog, "Scenes", /^Aldric Departs/), { key: "ArrowDown" });
    await waitFor(() =>
      expect(lastPreviewOrder(api)).toEqual(["exchange", "departs", "coronation"]),
    );
    await userEvent.click(undo);
    await waitFor(() => expect(lastPreviewOrder(api)).toEqual(ORDER));
    fireEvent.keyDown(window, { key: "z", ctrlKey: true, shiftKey: true });
    await waitFor(() =>
      expect(lastPreviewOrder(api)).toEqual(["exchange", "departs", "coronation"]),
    );
  });

  it("compares an alternative order and keeps the one that holds together", async () => {
    const api = bookApi();
    judging(api);
    const { dialog } = await openEditor(api);
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Compare an alternative" }),
    );
    const alternative = await within(dialog).findByRole("list", {
      name: "Alternative order",
    });
    fireEvent.keyDown(
      within(alternative).getByRole("listitem", { name: /^Aldric Departs/ }),
      { key: "ArrowDown" },
    );
    const compare = within(dialog).getByRole("group", { name: "Compare the two orders" });
    expect(await within(compare).findByText("2 problems")).toBeInTheDocument();
    expect(await within(compare).findByText("No problems")).toBeInTheDocument();
    expect(
      within(compare).getByText("Holds together better").closest(".cw-compare-card"),
    ).toHaveTextContent("Alternative");
    expect(within(dialog).getByRole("button", { name: "Save changes" })).toBeDisabled();

    await userEvent.click(within(compare).getByRole("button", { name: "Keep B" }));
    expect(
      within(dialog).queryByRole("list", { name: "Alternative order" }),
    ).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.callsTo("updatePlotline")).toHaveLength(1));
    const [, id, body, rev] = api.callsTo("updatePlotline")[0] as [
      string,
      string,
      { events: string[] },
      number,
    ];
    expect([id, body.events, rev]).toEqual([
      "road",
      ["exchange", "departs", "coronation"],
      1,
    ]);
  });

  it("explains a save someone else's edit beat, and offers their version", async () => {
    const { api, dialog } = await openEditor();
    api.refuse("updatePlotline", 409, "REVISION_CONFLICT");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(
      await within(dialog).findByText(/Someone else changed this thread/),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Reload their version" }),
    ).toBeInTheDocument();
  });

  it("does not read a deleted thread again on the way out", async () => {
    const { api, dialog, location } = await openEditor();
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete thread" }));
    const before = api.callsTo("getPlotline").length;
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(location.current()).toBe("#/ember-pact"));
    await screen.findByRole("heading", { level: 1, name: "The Ember Pact" });
    const after = api.callsTo("getPlotline").slice(before);
    expect(after.filter((args) => args[1] === "road")).toEqual([]);
  });

  it("offers to fold the thread into the ones that continue into it", async () => {
    const { api, dialog, location } = await openEditor();
    api.refuse("deletePlotline", 409, "PLOTLINE_IN_USE", { plotlines: ["shadow"] });
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete thread" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    const offer = await screen.findByRole("dialog", {
      name: "Other threads continue into this one",
    });
    expect(within(offer).getByText("The Spy's Shadow")).toBeInTheDocument();
    await userEvent.click(
      within(offer).getByRole("button", { name: "Copy in and delete" }),
    );
    await waitFor(() => expect(location.current()).toBe("#/ember-pact"));
    expect(api.callsTo("deletePlotline").map((args) => args[3])).toEqual([false, true]);
  });

  it("writes a new thread, its id following its name, and goes to it", async () => {
    const api = fakeApi();
    const { location } = renderWorkspace("#/ember-pact", api);
    await userEvent.click(await screen.findByRole("button", { name: "New thread" }));
    const dialog = await screen.findByRole("dialog", { name: "New thread" });
    await userEvent.type(within(dialog).getByLabelText("Name"), "The Long Way");
    expect(within(dialog).getByLabelText("Id")).toHaveValue("the-long-way");
    expect(within(dialog).getByRole("button", { name: "Create thread" })).toBeDisabled();
    await userEvent.type(
      within(dialog).getByRole("combobox", { name: "Add a scene" }),
      "Harbor",
    );
    await userEvent.click(
      await within(dialog).findByRole("option", { name: /The Harbor Exchange/ }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Create thread" }));
    await waitFor(() => expect(location.current()).toBe("#/ember-pact/the-long-way"));
    const [, id, body] = api.callsTo("createPlotline")[0] as [
      string,
      string,
      { title: string; events: string[] },
    ];
    expect([id, body.title, body.events]).toEqual([
      "the-long-way",
      "The Long Way",
      ["exchange"],
    ]);
  });
});

describe("historyKey", () => {
  it.each<[Partial<KeyboardEvent>, string | null]>([
    [{ key: "z", metaKey: true }, "undo"],
    [{ key: "Z", ctrlKey: true, shiftKey: true }, "redo"],
    [{ key: "y", ctrlKey: true }, "redo"],
    [{ key: "z" }, null],
    [{ key: "s", metaKey: true }, null],
  ])("reads %j as %s", (e, expected) => {
    expect(
      historyKey({ key: "", metaKey: false, ctrlKey: false, shiftKey: false, ...e }),
    ).toBe(expected);
  });
});
