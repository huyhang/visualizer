import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWorkspace } from "../../test/renderChronos";
import { graph } from "../../test/fixtures";
import type { TimelineEvent } from "../../api/types";
import { castItems, graphItems, sceneItems } from "./CommandPalette";
import { shortcutLabel } from "../common/keys";

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

  it("finds a scene on no thread, and opens it", async () => {
    renderWorkspace("#/ember-pact");
    await userEvent.click(await screen.findByRole("button", { name: /Search or jump to/ }));
    await userEvent.type(screen.getByRole("combobox"), "for later");
    await screen.findByRole("option", { name: /A Scene For Later/ });
    await userEvent.keyboard("{Enter}");
    const panel = await screen.findByRole("complementary", { name: "Details" });
    expect(
      await within(panel).findByRole("heading", { name: "A Scene For Later" }),
    ).toBeInTheDocument();
  });

  it("offers places, books and the calendar library before anything is typed", async () => {
    renderWorkspace("#/ember-pact");
    await userEvent.click(await screen.findByRole("button", { name: /Search or jump to/ }));
    const listed = (await screen.findAllByRole("option")).map((o) => o.textContent ?? "");
    expect(listed.some((t) => t.startsWith("Calendar library"))).toBe(true);
    expect(listed.some((t) => t.startsWith("The Ember Pact"))).toBe(true);
    expect(listed.some((t) => t.includes("Scene ·"))).toBe(false);
  });

  it("keeps the option the arrows reach in view", async () => {
    const seen = vi.spyOn(Element.prototype, "scrollIntoView");
    renderWorkspace("#/ember-pact");
    await userEvent.click(await screen.findByRole("button", { name: /Search or jump to/ }));
    await screen.findAllByRole("option");
    seen.mockClear();
    await userEvent.keyboard("{ArrowDown}");
    const active = screen.getAllByRole("option")[1];
    expect(seen.mock.contexts).toContain(active);
    seen.mockRestore();
  });

  it("starts in its search box and gives focus back to what opened it", async () => {
    renderWorkspace("#/ember-pact");
    const opener = await screen.findByRole("button", { name: /Search or jump to/ });
    await userEvent.click(opener);
    expect(
      await screen.findByRole("combobox", { name: "Search or jump to" }),
    ).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    await vi.waitFor(() => expect(opener).toHaveFocus());
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

  it("offers every thread and goal in the book", () => {
    const items = graphItems("ember-pact", graph(), sinks);
    const kinds = items.map((i) => i.key.split(":")[0]);
    expect(kinds.filter((k) => k === "thread")).toHaveLength(3);
    expect(kinds.filter((k) => k === "goal")).toHaveLength(3);
  });

  it("offers nothing before the graph arrives", () => {
    expect(graphItems("ember-pact", undefined, sinks)).toEqual([]);
  });
});

describe("sceneItems", () => {
  const sinks = { go: vi.fn(), inspect: vi.fn(), actions: {} };
  const row = (id: string, title: string, when: string | null) =>
    ({ id, title, scheduled: when !== null, when: when ?? "unscheduled" }) as TimelineEvent;

  it.each<[TimelineEvent, string]>([
    [row("exchange", "The Harbor Exchange", "Day 3 → Day 4"), "Scene · Day 3 → Day 4"],
    [row("later", "A Scene For Later", null), "Scene · unscheduled"],
  ])("dates %j as the listing does", (scene, hint) => {
    const [item] = sceneItems([scene], sinks);
    expect(item).toMatchObject({ label: scene.title, hint, searchOnly: true });
  });
});

describe("shortcutLabel", () => {
  it.each<[boolean, string]>([
    [true, "⌘K"],
    [false, "Ctrl K"],
  ])("on a Mac %s, says %s", (mac, label) => {
    expect(shortcutLabel("K", mac)).toBe(label);
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
