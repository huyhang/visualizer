import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fakeApi } from "../../test/fakeApi";
import { report } from "../../test/fixtures";
import { renderWorkspace } from "../../test/renderChronos";
import { NOTES_KEY } from "./IssuesView";
import { typingIn } from "./useTriage";

const ISSUES = "#/ember-pact/~issues";

describe("the report", () => {
  it("leads with the verdict and lists each kind of problem", async () => {
    renderWorkspace(ISSUES);
    expect(
      await screen.findByText("A character in two places at once"),
    ).toBeInTheDocument();
    expect(screen.getByText("Threads that do not reach the ending")).toBeInTheDocument();
    expect(document.querySelector(".cw-verdict")).toHaveTextContent(
      /2 problems\s*·\s*1 scene still waiting for a time/,
    );
  });

  it("reads the articles a message quotes as their titles", async () => {
    renderWorkspace(ISSUES);
    expect(await screen.findByText(/'Sir Aldric' cannot be here/)).toBeInTheDocument();
  });

  it("says so when there is nothing to fix", async () => {
    const api = fakeApi();
    api.reportValue = {
      ...report(),
      problems: [],
      notes: [],
      summary: { problems: 0, notes: 0, unscheduled: 0 },
    };
    renderWorkspace(ISSUES, api);
    expect(
      await screen.findByText("Nothing to fix — this book holds together."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Triage/ })).not.toBeInTheDocument();
  });

  it("folds the notes away and remembers that it did", async () => {
    const { store } = renderWorkspace(ISSUES);
    await screen.findByText("Goals still waiting for a scene");
    await userEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByText("Goals still waiting for a scene")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show 2 notes" })).toBeInTheDocument();
    expect(store.data[NOTES_KEY]).toBe("closed");
  });

  it("narrows to one thread from the rollup, and back", async () => {
    renderWorkspace(ISSUES);
    const rollup = await screen.findByRole("heading", { name: "By thread" });
    const section = rollup.closest("section") as HTMLElement;
    await userEvent.click(
      within(section).getByRole("button", { name: /The Knight's Road/ }),
    );
    expect(
      screen.queryByText("Threads that do not reach the ending"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("A character in two places at once")).toBeInTheDocument();
    await userEvent.click(
      within(section).getByRole("button", { name: /The Knight's Road/ }),
    );
    expect(screen.getByText("Threads that do not reach the ending")).toBeInTheDocument();
  });
});

describe("triage", () => {
  it("walks the issues one at a time, each open beside the list", async () => {
    renderWorkspace(ISSUES);
    await userEvent.click(await screen.findByRole("button", { name: "Triage 4 issues" }));
    expect(screen.getByText("1 of 4")).toBeInTheDocument();
    const panel = await screen.findByRole("complementary", { name: "Details" });
    expect(
      await within(panel).findByRole("heading", { name: "Aldric Departs" }),
    ).toBeInTheDocument();

    await userEvent.keyboard("j");
    expect(screen.getByText("2 of 4")).toBeInTheDocument();
    expect(
      await within(panel).findByRole("heading", { name: "Aldric Seen At Emberport" }),
    ).toBeInTheDocument();

    await userEvent.keyboard("j");
    expect(
      await within(panel).findByRole("heading", { name: "Establish who was where" }),
    ).toBeInTheDocument();

    await userEvent.keyboard("k");
    expect(screen.getByText("2 of 4")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByText("2 of 4")).not.toBeInTheDocument();
  });

  it("moves up to the next issue when the one it was on is fixed", async () => {
    const api = fakeApi();
    const { client } = renderWorkspace(ISSUES, api);
    await userEvent.click(await screen.findByRole("button", { name: "Triage 4 issues" }));
    await userEvent.keyboard("j");
    expect(screen.getByText("2 of 4")).toBeInTheDocument();

    const fixed = report();
    fixed.problems = fixed.problems.slice(0, 1);
    api.reportValue = fixed;
    await act(() => client.invalidateQueries());
    expect(await screen.findByText("2 of 3")).toBeInTheDocument();
    expect(
      screen.queryByText("Threads that do not reach the ending"),
    ).not.toBeInTheDocument();
  });

  it("starts where a click puts it", async () => {
    renderWorkspace(ISSUES);
    await userEvent.click(
      (
        await screen.findAllByRole("button", { name: "Look at this issue" })
      )[1] as HTMLElement,
    );
    expect(screen.getByText("2 of 4")).toBeInTheDocument();
  });
});

describe("typingIn", () => {
  it.each<[string, boolean]>([
    ["input", true],
    ["textarea", true],
    ["select", true],
    ["button", false],
    ["div", false],
  ])("treats a key in a <%s> as typing: %s", (tag, expected) => {
    expect(typingIn(document.createElement(tag))).toBe(expected);
  });

  it("counts nothing as typing when there is no target", () => {
    expect(typingIn(null)).toBe(false);
  });
});
