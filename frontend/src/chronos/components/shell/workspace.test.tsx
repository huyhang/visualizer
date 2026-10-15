import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWorkspace } from "../../test/renderChronos";

describe("the workspace", () => {
  it("opens on the shelf and goes into a book", async () => {
    const { location } = renderWorkspace("#/");
    expect(await screen.findByRole("heading", { name: "Your books" })).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("link", { name: /The Ember Pact/ }));
    expect(location.current()).toBe("#/ember-pact");
    expect(
      await screen.findByRole("link", { name: /The Knight's Road/ }),
    ).toBeInTheDocument();
  });

  it("follows the address bar from one book screen to another", async () => {
    const { location } = renderWorkspace("#/ember-pact");
    await screen.findByRole("link", { name: /The Knight's Road/ });
    act(() => location.push("#/ember-pact/~issues"));
    expect(await screen.findByRole("heading", { name: "Issues" })).toBeInTheDocument();
    act(() => location.push("#/"));
    expect(await screen.findByRole("heading", { name: "Your books" })).toBeInTheDocument();
  });

  it("keeps the report's problem count in the sidebar", async () => {
    renderWorkspace("#/ember-pact");
    const nav = await screen.findByRole("navigation", { name: "This book" });
    expect(await within(nav).findByLabelText("2 problems")).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /Threads/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("offers the classic page at the same place", async () => {
    renderWorkspace("#/ember-pact/~issues");
    expect(await screen.findByRole("link", { name: /Classic view/ })).toHaveAttribute(
      "href",
      "/classic#/ember-pact/~issues",
    );
  });
});
