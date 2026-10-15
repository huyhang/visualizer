import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWorkspace } from "../../test/renderChronos";
import { graph } from "../../test/fixtures";
import { castItems, graphItems } from "./CommandPalette";

describe("the command palette", () => {
  it("opens on ⌘K and jumps to a thread", async () => {
    const { location } = renderWorkspace("#/ember-pact");
    await screen.findByRole("link", { name: /The Knight's Road/ });
    await userEvent.keyboard("{Meta>}k{/Meta}");
    const input = await screen.findByRole("combobox", { name: "Search or jump to" });
    await userEvent.type(input, "spy shadow");
    await userEvent.keyboard("{Enter}");
    expect(location.current()).toBe("#/ember-pact/shadow");
  });

  it("opens a scene beside the page rather than leaving it", async () => {
    const { location } = renderWorkspace("#/ember-pact");
    await userEvent.click(await screen.findByRole("button", { name: /Search or jump to/ }));
    await userEvent.type(screen.getByRole("combobox"), "harbor exchange");
    await userEvent.keyboard("{Enter}");
    const panel = await screen.findByRole("complementary", { name: "Details" });
    expect(
      await within(panel).findByRole("heading", { name: "The Harbor Exchange" }),
    ).toBeInTheDocument();
    expect(location.current()).toBe("#/ember-pact");
  });

  it("moves through what it found with the arrows", async () => {
    renderWorkspace("#/ember-pact");
    await userEvent.click(await screen.findByRole("button", { name: /Search or jump to/ }));
    await userEvent.type(screen.getByRole("combobox"), "aldric");
    const options = await screen.findAllByRole("option");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
  });

  it("says when nothing matches", async () => {
    renderWorkspace("#/");
    await userEvent.click(await screen.findByRole("button", { name: /Search or jump to/ }));
    await userEvent.type(screen.getByRole("combobox"), "dragon");
    expect(await screen.findByText("Nothing matches “dragon”.")).toBeInTheDocument();
  });
});

describe("graphItems", () => {
  const sinks = { go: vi.fn(), inspect: vi.fn(), actions: {} };

  it("offers every thread, scene and goal in the book", () => {
    const items = graphItems("ember-pact", graph(), sinks);
    const kinds = items.map((i) => i.key.split(":")[0]);
    expect(kinds.filter((k) => k === "thread")).toHaveLength(3);
    expect(kinds.filter((k) => k === "scene")).toHaveLength(5);
    expect(kinds.filter((k) => k === "goal")).toHaveLength(3);
  });

  it("dates a scene in its hint", () => {
    const exchange = graphItems("ember-pact", graph(), sinks).find(
      (i) => i.key === "scene:exchange",
    );
    expect(exchange?.hint).toBe("Scene · Day 3");
  });

  it("offers nothing before the graph arrives", () => {
    expect(graphItems("ember-pact", undefined, sinks)).toEqual([]);
  });
});

describe("castItems", () => {
  const lyra = { database: "w", collection: "characters", id: "lyra" };

  it("offers to open each person and to follow them", () => {
    const follow = vi.fn();
    const inspect = vi.fn();
    const items = castItems([{ ref: lyra, scenes: 3, title: "Lyra Vane" }], {
      go: vi.fn(),
      inspect,
      actions: {},
      follow,
    });
    expect(items.map((i) => [i.label, i.hint])).toEqual([
      ["Lyra Vane", "characters · 3 scenes"],
      ["Follow Lyra Vane", "Fade every scene they are not in"],
    ]);
    items[0]?.run();
    items[1]?.run();
    expect(inspect).toHaveBeenCalledWith({ kind: "article", ref: lyra });
    expect(follow).toHaveBeenCalledWith(lyra);
  });
});

describe("following from the palette", () => {
  it("finds a character by name and follows them", async () => {
    renderWorkspace("#/ember-pact");
    await screen.findByRole("option", { name: /Lyra · \d+ scenes?/ });
    await userEvent.keyboard("{Control>}k{/Control}");
    await userEvent.type(
      await screen.findByRole("combobox", { name: "Search or jump to" }),
      "follow lyra",
    );
    await userEvent.keyboard("{Enter}");
    expect(
      await screen.findByRole("button", { name: "Stop following" }),
    ).toBeInTheDocument();
  });
});
