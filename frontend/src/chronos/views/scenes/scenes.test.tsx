import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fakeApi, type FakeApi } from "../../test/fakeApi";
import { renderWorkspace } from "../../test/renderChronos";
import { whenLines } from "./SceneList";

const SCENES = "#/ember-pact/~scenes";

async function listMode(api?: FakeApi) {
  const view = renderWorkspace(SCENES, api);
  await userEvent.click(await screen.findByRole("button", { name: "List" }));
  const list = await screen.findByRole("list", { name: "Scenes" });
  return { ...view, list };
}

const rowOf = (list: HTMLElement, title: string) =>
  within(list).getByRole("button", { name: title }).closest("li") as HTMLElement;

describe("the Scenes screen", () => {
  it("opens on the timeline, with the undated scenes on a shelf below", async () => {
    renderWorkspace(SCENES);
    expect(await screen.findByText("5 scheduled scenes")).toBeInTheDocument();
    expect(screen.getByText("1 unscheduled scene")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /Scene timeline/ })).toBeInTheDocument();
  });

  it("lists every scene with when, where and its threads", async () => {
    const { list } = await listMode();
    const row = rowOf(list, "The Harbor Exchange");
    expect(within(row).getByText("Day 3")).toBeInTheDocument();
    expect(await within(row).findByText("Emberport")).toBeInTheDocument();
    expect(await within(row).findByText("The Knight's Road")).toBeInTheDocument();
    // Once as its "when", once as the chip that says it still needs a time.
    expect(
      within(rowOf(list, "A Scene For Later")).getAllByText("unscheduled"),
    ).toHaveLength(2);
  });

  it("opens a scene beside the list", async () => {
    const { list } = await listMode();
    await userEvent.click(within(list).getByRole("button", { name: "Aldric Departs" }));
    const panel = await screen.findByRole("complementary", { name: "Details" });
    expect(
      await within(panel).findByRole("heading", { name: "Aldric Departs" }),
    ).toBeInTheDocument();
  });
});

describe("deleting a scene", () => {
  it("reads the scene first and deletes it with the revision it read", async () => {
    const { api, list } = await listMode();
    await userEvent.click(
      within(rowOf(list, "Lyra Infiltrates")).getByRole("button", {
        name: "Delete “Lyra Infiltrates”",
      }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(api.callsTo("deleteEvent")).toEqual([["ember-pact", "infiltrates", 1, false]]),
    );
    expect(api.callsTo("getEvent")[0]?.slice(0, 2)).toEqual(["ember-pact", "infiltrates"]);
  });

  it("offers to take a scene out of the threads using it, and does so on request", async () => {
    const api = fakeApi();
    api.refuse("deleteEvent", 409, "EVENT_IN_USE", { plotlines: ["road", "shadow"] });
    const { list } = await listMode(api);
    await userEvent.click(
      within(rowOf(list, "The Harbor Exchange")).getByRole("button", { name: /Delete/ }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Other threads use this scene",
    });
    expect(within(dialog).getByText("The Knight's Road")).toBeInTheDocument();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Take it out of them and delete" }),
    );
    await waitFor(() =>
      expect(api.callsTo("deleteEvent").at(-1)).toEqual([
        "ember-pact",
        "exchange",
        1,
        true,
      ]),
    );
  });

  it("refuses rather than leave a thread with no scenes", async () => {
    const api = fakeApi();
    api.refuse("deleteEvent", 409, "EVENT_IN_USE", { plotlines: ["tale"] });
    const { list } = await listMode(api);
    await userEvent.click(
      within(rowOf(list, "Aldric Seen At Emberport")).getByRole("button", {
        name: /Delete/,
      }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(
      await screen.findByRole("dialog", {
        name: "That would leave a thread with no scenes",
      }),
    ).toBeInTheDocument();
    expect(api.callsTo("deleteEvent")).toHaveLength(1);
  });

  it("explains that the book's ending cannot be deleted, without asking the server", async () => {
    const { api, list } = await listMode();
    await userEvent.click(
      within(rowOf(list, "The Coronation")).getByRole("button", { name: /Delete/ }),
    );
    expect(
      await screen.findByRole("dialog", { name: "This scene is the book's ending" }),
    ).toBeInTheDocument();
    expect(api.callsTo("deleteEvent")).toEqual([]);
  });

  it("explains a scene that changed since the page was drawn", async () => {
    const api = fakeApi();
    api.refuse("deleteEvent", 409, "REVISION_CONFLICT");
    const { list } = await listMode(api);
    await userEvent.click(
      within(rowOf(list, "Lyra Infiltrates")).getByRole("button", { name: /Delete/ }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Something changed while deleting",
    );
  });
});

describe("whenLines", () => {
  it.each<[string, string[]]>([
    ["Day 1 → Day 2", ["Day 1", "→ Day 2"]],
    ["Day 1", ["Day 1"]],
    ["unscheduled", ["unscheduled"]],
  ])("splits %j", (when, lines) => {
    expect(whenLines(when)).toEqual(lines);
  });
});
