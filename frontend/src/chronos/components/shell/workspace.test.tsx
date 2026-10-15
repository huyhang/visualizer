import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWorkspace } from "../../test/renderChronos";
import { CALENDAR_KEY } from "../../logic/calendarView";

describe("the workspace", () => {
  it("reads a book in the calendar remembered for it from the very first request", async () => {
    const { api } = renderWorkspace("#/ember-pact/~scenes", undefined, {
      [CALENDAR_KEY]: JSON.stringify({ "ember-pact": "earth" }),
    });
    await screen.findByRole("heading", { level: 1, name: "Scenes" });
    await vi.waitFor(() => expect(api.callsTo("getGraph").length).toBeGreaterThan(0));
    const asked = [
      ...api.callsTo("timelineEvents"),
      ...api.callsTo("getGraph"),
      ...api.callsTo("bookIssues"),
    ].map((args) => (args[1] as { calendar?: string | null } | undefined)?.calendar);
    expect(asked.length).toBeGreaterThan(0);
    expect(asked.filter((c) => c !== "earth")).toEqual([]);
  });

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
