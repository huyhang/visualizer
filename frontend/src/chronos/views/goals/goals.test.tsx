import { screen, within } from "@testing-library/react";
import { vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderWorkspace } from "../../test/renderChronos";

const diagram = async () => screen.findByRole("group", { name: /Goal dependencies/ });

describe("the goals screen", () => {
  it("draws a box per goal, prerequisites first", async () => {
    renderWorkspace("#/ember-pact/~goals");
    const boxes = within(await diagram()).getAllByRole("button");
    expect(boxes.map((b) => b.getAttribute("title")).sort()).toEqual([
      "Deliver the Ember Seal",
      "Establish who was where",
      "See the crown pressed",
    ]);
    expect(
      within(await diagram()).getByRole("button", {
        name: /^Deliver the Ember Seal: ✓ The Harbor Exchange, Day 3$/,
      }),
    ).toBeInTheDocument();
  });

  it("selects a goal through the address bar and opens its card", async () => {
    const { location } = renderWorkspace("#/ember-pact/~goals");
    await userEvent.click(
      within(await diagram()).getByRole("button", { name: /^Deliver the Ember Seal/ }),
    );
    expect(location.current()).toBe("#/ember-pact/~goals/seal");
    const card = await screen.findByRole("button", {
      name: /Deliver the Ember Seal.*achieved/,
      expanded: true,
    });
    expect(card).toBeInTheDocument();
    expect(screen.getByText("Needed by")).toBeInTheDocument();
  });

  it("keeps the selected goal's chain bright and lets the rest recede", async () => {
    renderWorkspace("#/ember-pact/~goals/crown");
    const group = await diagram();
    expect(
      within(group).getByRole("button", { name: /^See the crown pressed/ }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(group).getByRole("button", { name: /^Deliver the Ember Seal/ }),
    ).not.toHaveClass("is-dim");
    expect(
      within(group).getByRole("button", { name: /^Establish who was where/ }),
    ).toHaveClass("is-dim");
  });

  it("narrows the list, never the diagram", async () => {
    renderWorkspace("#/ember-pact/~goals");
    await diagram();
    await userEvent.type(screen.getByRole("searchbox", { name: "Filter goals" }), "crown");
    await vi.waitFor(() =>
      expect(document.querySelectorAll(".cw-goal-card")).toHaveLength(1),
    );
    expect(within(await diagram()).getAllByRole("button")).toHaveLength(3);
  });
});
