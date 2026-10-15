import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWorkspace } from "../../test/renderChronos";
import { nodeFades } from "./MapView";

const MAP = "#/ember-pact/~map";

async function mapReady() {
  return screen.findByRole("group", { name: "Threads on the map" });
}

const sceneRow = (container: HTMLElement, id: string) =>
  container.querySelector(`[data-scene="${id}"]`) as HTMLElement | null;

describe("the story map", () => {
  it("draws every thread of the book, its scenes and its curves", async () => {
    const { container } = renderWorkspace(MAP);
    const chips = within(await mapReady()).getAllByRole("button");
    expect(chips.map((c) => c.getAttribute("aria-pressed"))).toEqual([
      "true",
      "true",
      "true",
    ]);
    expect(
      await screen.findByRole("button", { name: "The Harbor Exchange" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Every thread in this book — 3.")).toBeInTheDocument();
    // road and shadow each run two edges; tale is one scene with none.
    expect(container.querySelectorAll(".cw-sg-edge")).toHaveLength(4);
    expect(container.querySelectorAll(".cw-sg-node")).toHaveLength(5);
  });

  it("puts scenes happening at once on one line, under a count", async () => {
    renderWorkspace(MAP);
    await mapReady();
    expect(screen.getByText("3 at once")).toBeInTheDocument();
  });

  it.each<[string, string]>([
    ["The Spy's Shadow", "#/ember-pact/~map/road,tale"],
    ["The Witness's Tale", "#/ember-pact/~map/road,shadow"],
  ])("writes the selection into the address when %s is ticked off", async (title, hash) => {
    const { location } = renderWorkspace(MAP);
    await userEvent.click(within(await mapReady()).getByRole("button", { name: title }));
    expect(location.current()).toBe(hash);
    expect(location.history).toHaveLength(1);
    expect(screen.getByText(/2 of 3 threads — 1 not shown/)).toBeInTheDocument();
  });

  it("arrives on the connected preset and rewrites the address to what it became", async () => {
    const { location } = renderWorkspace("#/ember-pact/road/connected");
    const chips = within(await mapReady());
    expect(chips.getByRole("button", { name: "The Witness's Tale" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(location.current()).toBe("#/ember-pact/~map/road,shadow");
  });

  it("follows the address when it changes under the map", async () => {
    const { location } = renderWorkspace(MAP);
    const chips = within(await mapReady());
    act(() => location.push("#/ember-pact/~map/tale"));
    expect(chips.getByRole("button", { name: "The Knight's Road" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(chips.getByRole("button", { name: "The Witness's Tale" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("says so when no thread is selected", async () => {
    renderWorkspace(MAP);
    await userEvent.click(await screen.findByRole("button", { name: "None" }));
    expect(screen.getByText("No threads selected")).toBeInTheDocument();
  });

  it("opens a scene beside the map from its title", async () => {
    renderWorkspace(MAP);
    await userEvent.click(
      await screen.findByRole("button", { name: "The Harbor Exchange" }),
    );
    const panel = await screen.findByRole("complementary", { name: "Details" });
    expect(
      await within(panel).findByRole("heading", { name: "The Harbor Exchange" }),
    ).toBeInTheDocument();
  });

  it("opens a scene in place from its twisty, and Escape closes it", async () => {
    const { container } = renderWorkspace(MAP);
    await mapReady();
    const row = sceneRow(container, "exchange") as HTMLElement;
    await userEvent.click(
      within(row).getByRole("button", { name: "Show this scene in full" }),
    );
    expect(
      await within(row).findByRole("button", { name: /Open beside the map/ }),
    ).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(
      within(row).queryByRole("button", { name: /Open beside the map/ }),
    ).not.toBeInTheDocument();
  });

  it("fades the scenes the followed character is not in", async () => {
    const { container } = renderWorkspace(MAP);
    await mapReady();
    const follow = await screen.findByRole("combobox", {
      name: "Follow a character, place or thing",
    });
    await screen.findByRole("option", { name: /Lyra/ });
    await userEvent.selectOptions(follow, "ember-pact/characters/lyra");
    expect(await screen.findByText(/2 of 5 scenes/)).toBeInTheDocument();
    expect(sceneRow(container, "departs")).toHaveClass("cw-faded");
    expect(sceneRow(container, "exchange")).not.toHaveClass("cw-faded");
    expect(sceneRow(container, "infiltrates")).not.toHaveClass("cw-faded");
  });

  it("marks a goal on the scene that delivers it, opening it beside the map", async () => {
    const { container } = renderWorkspace(MAP);
    await mapReady();
    const row = sceneRow(container, "exchange") as HTMLElement;
    await userEvent.click(
      within(row).getByRole("button", { name: /Deliver the Ember Seal/ }),
    );
    expect(
      await screen.findByRole("complementary", { name: "Details" }),
    ).toBeInTheDocument();
  });

  it("lists a pursued goal that lands nowhere shown, and hides goals on request", async () => {
    renderWorkspace(MAP);
    await mapReady();
    const strip = screen.getByRole("region", { name: "Not landed on the shown threads" });
    expect(within(strip).getByText("Establish who was where")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Hide goals" }));
    expect(
      screen.queryByRole("region", { name: "Not landed on the shown threads" }),
    ).not.toBeInTheDocument();
  });
});

describe("nodeFades", () => {
  const lens = { fades: (id: string) => id !== "kept" };
  it.each<[{ id: string; isBand: boolean; events: string[] | null }, boolean]>([
    [{ id: "kept", isBand: false, events: null }, false],
    [{ id: "gone", isBand: false, events: null }, true],
    [{ id: "~run", isBand: true, events: ["gone", "kept"] }, false],
    [{ id: "~run", isBand: true, events: ["gone", "lost"] }, true],
  ])("fades %j: %s", (node, expected) => {
    expect(nodeFades(lens, node)).toBe(expected);
  });
});
