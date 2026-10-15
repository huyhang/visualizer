import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWorkspace } from "../../test/renderChronos";
import { NARROW } from "../../hooks/useNarrow";
import { bookSections } from "./Sidebar";
import { to } from "../../logic/route";

/** The window answers the phone's media query as `phone` says. */
function asPhone(phone: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: phone && query === NARROW,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("the sidebar on a phone", () => {
  it("keeps only where to go in the strip, the rest in the View sheet", async () => {
    asPhone(true);
    renderWorkspace("#/ember-pact");
    const strip = await screen.findByRole("navigation", { name: "This book" });
    expect(within(strip).getByRole("link", { name: "Story map" })).toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Read dates in" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Library" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "View options" }));
    const sheet = await screen.findByRole("dialog", { name: "View" });
    expect(
      within(sheet).getByRole("combobox", { name: "Read dates in" }),
    ).toBeInTheDocument();
    expect(
      await within(sheet).findByRole("combobox", {
        name: "Follow a character, place or thing",
      }),
    ).toBeInTheDocument();
    expect(within(sheet).getByRole("link", { name: /Classic view/ })).toBeInTheDocument();
  });

  it("closes the sheet on the way to the library", async () => {
    asPhone(true);
    const { location } = renderWorkspace("#/ember-pact");
    await userEvent.click(await screen.findByRole("button", { name: "View options" }));
    const sheet = await screen.findByRole("dialog", { name: "View" });
    await userEvent.click(within(sheet).getByRole("link", { name: /Calendars/ }));
    expect(location.current()).toBe("#/~calendars");
    expect(screen.queryByRole("dialog", { name: "View" })).not.toBeInTheDocument();
  });

  it("says who is followed above the screen, and marks the View button", async () => {
    asPhone(true);
    renderWorkspace("#/ember-pact");
    await userEvent.click(await screen.findByRole("button", { name: "View options" }));
    const sheet = await screen.findByRole("dialog", { name: "View" });
    const picker = await within(sheet).findByRole("combobox", {
      name: "Follow a character, place or thing",
    });
    await within(sheet).findByRole("option", { name: /Sir Aldric/ });
    await userEvent.selectOptions(
      picker,
      within(sheet).getByRole("option", { name: /Sir Aldric/ }),
    );
    await userEvent.keyboard("{Escape}");
    expect(
      await screen.findByText(/Following Sir Aldric · \d+ scenes/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "View options (some are set)" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Stop following" }));
    expect(screen.getByRole("button", { name: "View options" })).toBeInTheDocument();
  });
});

describe("the sidebar on a wider screen", () => {
  it("keeps the calendar, Follow and the library beside the screens, with no sheet", async () => {
    asPhone(false);
    renderWorkspace("#/ember-pact");
    expect(
      await screen.findByRole("combobox", { name: "Read dates in" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Library" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /View options/ })).not.toBeInTheDocument();
  });
});

describe("bookSections", () => {
  it.each<[string, string | undefined]>([
    ["Threads", undefined],
    ["Scenes", undefined],
    ["Goals", undefined],
    ["Story map", "Map"],
    ["Issues", undefined],
  ])("gives %s the tab name %s on a phone", (label, short) => {
    const section = bookSections(to.threads("b"), "b", 0).find((s) => s.label === label);
    expect(section?.short).toBe(short);
  });
});
