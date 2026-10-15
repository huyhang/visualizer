import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChronosApp } from "../../ChronosApp";
import { fakeApi } from "../../test/fakeApi";
import { harness, renderWorkspace } from "../../test/renderChronos";
import { testQueryClient } from "../../../test/render";
import scenesCss from "../../styles/scenes.css?raw";

async function timeline() {
  return screen.findByRole("heading", { level: 1, name: "The Knight's Road" });
}

const titles = () =>
  Array.from(document.querySelectorAll(".cw-pl-row .cw-pl-card-title")).map(
    (el) => el.textContent,
  );

describe("one thread's timeline", () => {
  it("draws its scenes in story order with what is wrong marked on them", async () => {
    renderWorkspace("#/ember-pact/road");
    await timeline();
    expect(titles()).toEqual(["Aldric Departs", "The Harbor Exchange", "The Coronation"]);
    expect(screen.getByText("1 problem in this thread")).toBeInTheDocument();
    // The finding quotes the article by id; the page reads it as its title.
    expect(await screen.findByText(/'Sir Aldric' cannot be here/)).toBeInTheDocument();
  });

  it("draws its cards in classes the Scenes screen's stylesheet does not style", async () => {
    renderWorkspace("#/ember-pact/road");
    await timeline();
    const classes = new Set(
      Array.from(document.querySelectorAll(".cw-pl-row *")).flatMap((el) =>
        Array.from(el.classList),
      ),
    );
    // scenes.css sizes its own cards to a fixed height; shared names clipped these.
    const styled = [...classes].filter((c) =>
      new RegExp(`\\.${c}(?![\\w-])`).test(scenesCss),
    );
    expect(styled).toEqual([]);
  });

  it("marks the scene's role in the weave and the goals it delivers", async () => {
    renderWorkspace("#/ember-pact/road");
    await timeline();
    const exchange = document.querySelector('[data-event="exchange"]') as HTMLElement;
    expect(within(exchange).getByText("Convergence")).toBeInTheDocument();
    expect(
      within(exchange).getByRole("button", { name: /Deliver the Ember Seal/ }),
    ).toBeInTheDocument();
    const ending = document.querySelector('[data-event="coronation"]') as HTMLElement;
    expect(within(ending).getByText("Ending")).toBeInTheDocument();
  });

  it("hides the marks in focus mode, says what it is hiding, and remembers", async () => {
    const { store } = renderWorkspace("#/ember-pact/road");
    await timeline();
    await userEvent.click(screen.getByRole("button", { name: "Hide problems" }));
    expect(screen.getByRole("button", { name: "Show 1 problem" })).toBeInTheDocument();
    expect(document.querySelector(".cw-plotline")).toHaveClass("is-focus");
    expect(store.data["chronos-focus"]).toBe("1");
  });

  it("starts in focus mode when the writer left it on", async () => {
    const h = harness("#/ember-pact/road");
    h.store.set("chronos-focus", "1");
    render(<ChronosApp deps={h.deps} client={testQueryClient()} />);
    await timeline();
    expect(screen.getByRole("button", { name: "Show 1 problem" })).toBeInTheDocument();
  });

  it("arrives at the scene the address names", async () => {
    renderWorkspace("#/ember-pact/road/at/exchange");
    await timeline();
    expect(document.querySelector('[data-event="exchange"]')).toHaveClass("is-focused");
    expect(document.querySelector('[data-event="departs"]')).not.toHaveClass("is-focused");
  });

  it("arrives once: opening the inspector later does not scroll back", async () => {
    const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
    renderWorkspace("#/ember-pact/road/at/exchange");
    await timeline();
    await vi.waitFor(() => expect(scrolled).toHaveBeenCalled());
    scrolled.mockClear();
    await userEvent.click(screen.getByRole("button", { name: "The Coronation" }));
    await screen.findByRole("complementary", { name: "Details" });
    await new Promise((r) => requestAnimationFrame(r));
    expect(scrolled).not.toHaveBeenCalled();
    scrolled.mockRestore();
  });

  it("lets a scene from another thread, opened on arrival, be closed", async () => {
    renderWorkspace("#/ember-pact/road/at/sighting");
    await timeline();
    const details = await screen.findByRole("complementary", { name: "Details" });
    expect(
      await within(details).findByRole("heading", { name: "Aldric Seen At Emberport" }),
    ).toBeInTheDocument();
    await userEvent.click(within(details).getByRole("button", { name: "Close the panel" }));
    await new Promise((r) => requestAnimationFrame(r));
    expect(
      screen.queryByRole("complementary", { name: "Details" }),
    ).not.toBeInTheDocument();
  });

  it("opens a scene beside the timeline from its title", async () => {
    renderWorkspace("#/ember-pact/road");
    await timeline();
    await userEvent.click(screen.getByRole("button", { name: "The Harbor Exchange" }));
    const details = await screen.findByRole("complementary", { name: "Details" });
    expect(
      await within(details).findByRole("heading", { name: "The Harbor Exchange" }),
    ).toBeInTheDocument();
  });

  it("offers the connected plots when the thread meets another", async () => {
    const api = fakeApi();
    const road = api.plotlines.get("road");
    if (road) {
      api.plotlines.set("road", {
        ...road,
        effective_events: road.effective_events.map((e) =>
          typeof e === "string" || e.id !== "exchange"
            ? e
            : { ...e, shared_with: ["shadow"] },
        ),
      });
    }
    const { location } = renderWorkspace("#/ember-pact/road", api);
    await timeline();
    const pushed = vi.spyOn(location, "push");
    await userEvent.click(
      await screen.findByRole("link", { name: /Connected plots \(1\)/ }),
    );
    // The map then rewrites the preset to the selection it stands for.
    expect(pushed).toHaveBeenCalledWith("#/ember-pact/road/connected");
  });

  it("says when a thread has no scenes", async () => {
    const api = fakeApi();
    const road = api.plotlines.get("road");
    if (road) api.plotlines.set("road", { ...road, events: [], effective_events: [] });
    renderWorkspace("#/ember-pact/road", api);
    expect(await screen.findByText("This thread has no scenes yet")).toBeInTheDocument();
  });
});
