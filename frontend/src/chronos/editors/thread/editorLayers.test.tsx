import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fakeApi, type FakeApi } from "../../test/fakeApi";
import { summary } from "../../test/fixtures";
import { renderWorkspace } from "../../test/renderChronos";

const ORDER = ["departs", "exchange", "coronation"];

function bookApi(): FakeApi {
  const api = fakeApi();
  const road = api.plotlines.get("road");
  if (road) api.plotlines.set("road", { ...road, events: [...ORDER] });
  return api;
}

async function openEditor(api: FakeApi = bookApi()) {
  const harness = renderWorkspace("#/ember-pact/road", api);
  await userEvent.click(await screen.findByRole("button", { name: "Edit thread" }));
  const dialog = await screen.findByRole("dialog", { name: "Edit thread" });
  await within(dialog).findByRole("list", { name: "Scenes" });
  return { ...harness, dialog };
}

/** The order as it stands, read even while another dialog is over the editor. */
const titles = (dialog: HTMLElement) =>
  within(within(dialog).getByRole("list", { name: "Scenes", hidden: true }))
    .getAllByRole("listitem", { hidden: true })
    .map((li) => li.getAttribute("data-event"));

const row = (dialog: HTMLElement, name: RegExp) =>
  within(within(dialog).getByRole("list", { name: "Scenes" })).getByRole("listitem", {
    name,
  });

describe("the thread editor's keys", () => {
  it("leaves focus in a field typed into after a keyboard move", async () => {
    const { dialog } = await openEditor();
    const departs = row(dialog, /^Aldric Departs/);
    departs.focus();
    fireEvent.keyDown(departs, { key: "ArrowDown" });
    await waitFor(() =>
      expect(titles(dialog)).toEqual(["exchange", "departs", "coronation"]),
    );
    expect(row(dialog, /^Aldric Departs/)).toHaveFocus();

    const name = within(dialog).getByLabelText("Name");
    await userEvent.click(name);
    await userEvent.type(name, "xy{Backspace}");
    expect(name).toHaveFocus();
    expect(name).toHaveValue("The Knight's Roadx");
    // Backspace fixed the typo, not the order.
    expect(titles(dialog)).toEqual(["exchange", "departs", "coronation"]);
  });

  it("closes an open type-ahead on Escape, not the editor", async () => {
    const { dialog } = await openEditor();
    const search = within(dialog).getByRole("combobox", { name: /scene/i });
    await userEvent.type(search, "lyra");
    expect(search).toHaveAttribute("aria-expanded", "true");
    await userEvent.keyboard("{Escape}");
    expect(search).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("dialog", { name: "Edit thread" })).toBeInTheDocument();
  });

  it("leaves ⌘Z to a scene dialog opened over it", async () => {
    const { dialog } = await openEditor();
    fireEvent.keyDown(row(dialog, /^Aldric Departs/), { key: "ArrowDown" });
    await waitFor(() =>
      expect(titles(dialog)).toEqual(["exchange", "departs", "coronation"]),
    );
    await userEvent.click(
      within(row(dialog, /^The Harbor Exchange/)).getByRole("button", {
        name: "Edit this scene",
      }),
    );
    const scene = await screen.findByRole("dialog", { name: /Edit “The Harbor Exchange”/ });
    fireEvent.keyDown(scene, { key: "z", ctrlKey: true });
    expect(titles(dialog)).toEqual(["exchange", "departs", "coronation"]);
  });

  it("does not open the palette over it", async () => {
    await openEditor();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(
      screen.queryByRole("dialog", { name: "Search or jump to" }),
    ).not.toBeInTheDocument();
  });

  it("peeks at a scene a finding points at that is not in this order", async () => {
    const api = bookApi();
    const preview = api.previewPlotline;
    api.previewPlotline = async (b, candidate, opts) => ({
      ...(await preview(b, candidate, opts)),
      effective_events: candidate.events.map((e) =>
        summary(
          e,
          e === "departs"
            ? {
                findings: [
                  {
                    code: "TEMPORAL_CONFLICT",
                    severity: "conflict",
                    message: "Aldric cannot be in two places at once.",
                    events: ["sighting"],
                    refs: [],
                  },
                ],
              }
            : {},
        ),
      ),
    });
    const { dialog } = await openEditor(api);
    await userEvent.click(await within(dialog).findByRole("button", { name: "show" }));
    const peek = await screen.findByRole("dialog", { name: "Scene" });
    expect(
      await within(peek).findByRole("heading", { name: "Aldric Seen At Emberport" }),
    ).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Scene" })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Edit thread" })).toBeInTheDocument();
  });
});

describe("what the classic editor could do", () => {
  it("inserts a scene before the first one", async () => {
    const { dialog } = await openEditor();
    await userEvent.click(
      within(row(dialog, /^Aldric Departs/)).getByRole("button", {
        name: "Insert a scene before this one",
      }),
    );
    const search = await within(dialog).findByRole("combobox", {
      name: "Insert before “Aldric Departs”",
    });
    await userEvent.type(search, "lyra");
    await userEvent.click(
      await within(dialog).findByRole("option", { name: /Lyra Infiltrates/ }),
    );
    await waitFor(() =>
      expect(titles(dialog)).toEqual(["infiltrates", "departs", "exchange", "coronation"]),
    );
  });

  it("writes a new goal and adds it to the thread", async () => {
    const { api, dialog } = await openEditor();
    await userEvent.click(within(dialog).getByRole("button", { name: "New goal" }));
    const goal = await screen.findByRole("dialog", { name: "New goal" });
    await userEvent.type(within(goal).getByLabelText("Name"), "Keep the road open");
    await userEvent.click(within(goal).getByRole("button", { name: "Create goal" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "New goal" })).not.toBeInTheDocument(),
    );
    expect(await within(dialog).findByText("Keep the road open")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.callsTo("updatePlotline")).toHaveLength(1));
    expect((api.callsTo("updatePlotline")[0]?.[2] as { goals: string[] }).goals).toContain(
      "keep-the-road-open",
    );
  });

  it("hides the problems, as the thread screen does, and remembers", async () => {
    const { dialog, store } = await openEditor();
    await userEvent.click(within(dialog).getByRole("button", { name: "Hide problems" }));
    expect(dialog.querySelector(".cw-editor")).toHaveClass("is-focus");
    expect(store.data["chronos-focus"]).toBe("1");
  });
});

describe("leaving the thread editor", () => {
  it.each(["Escape", "Cancel"])(
    "closes at once on %s when nothing changed",
    async (how) => {
      const { dialog } = await openEditor();
      if (how === "Escape") await userEvent.keyboard("{Escape}");
      else await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
      await waitFor(() =>
        expect(
          screen.queryByRole("dialog", { name: "Edit thread" }),
        ).not.toBeInTheDocument(),
      );
    },
  );

  it.each(["Escape", "Cancel"])("asks first on %s when there is a draft", async (how) => {
    const { dialog } = await openEditor();
    fireEvent.keyDown(row(dialog, /^Aldric Departs/), { key: "ArrowDown" });
    await waitFor(() =>
      expect(titles(dialog)).toEqual(["exchange", "departs", "coronation"]),
    );
    if (how === "Escape") await userEvent.keyboard("{Escape}");
    else await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    const ask = await screen.findByRole("dialog", { name: "Discard your changes?" });
    await userEvent.click(within(ask).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("dialog", { name: "Edit thread" })).toBeInTheDocument();
    if (how === "Escape") await userEvent.keyboard("{Escape}");
    else await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await userEvent.click(
      within(
        await screen.findByRole("dialog", { name: "Discard your changes?" }),
      ).getByRole("button", { name: "Discard changes" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Edit thread" })).not.toBeInTheDocument(),
    );
  });
});
