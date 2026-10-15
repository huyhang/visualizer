import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChronosApiError } from "../../api/errors";
import { fakeApi } from "../../test/fakeApi";
import { graph } from "../../test/fixtures";
import { renderWorkspace } from "../../test/renderChronos";
import { akashaArticleUrl } from "./ArticlePane";
import { goalsDeliveredAt, threadsThrough } from "./ScenePane";

async function openFromIssues() {
  const h = renderWorkspace("#/ember-pact/~issues");
  await userEvent.click(
    (
      await screen.findAllByRole("button", { name: "Look at this issue" })
    )[0] as HTMLElement,
  );
  const panel = await screen.findByRole("complementary", { name: "Details" });
  return { ...h, panel };
}

describe("the inspector", () => {
  it("shows a scene in full: where, who, threads", async () => {
    const { panel } = await openFromIssues();
    expect(
      await within(panel).findByRole("heading", { name: "Aldric Departs" }),
    ).toBeInTheDocument();
    expect(within(panel).getByText("Day 1 → Day 2")).toBeInTheDocument();
    expect(
      await within(panel).findByRole("button", { name: /Highkeep/ }),
    ).toBeInTheDocument();
    expect(
      within(panel).getByRole("button", { name: /The Knight's Road/ }),
    ).toBeInTheDocument();
  });

  it("follows a link inside it and comes back", async () => {
    const { panel } = await openFromIssues();
    await userEvent.click(await within(panel).findByRole("button", { name: /Sir Aldric/ }));
    expect(
      await within(panel).findByRole("heading", { name: "Sir Aldric" }),
    ).toBeInTheDocument();
    expect(within(panel).getByText("Sworn to Highkeep.")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Back" }));
    expect(
      await within(panel).findByRole("heading", { name: "Aldric Departs" }),
    ).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    await openFromIssues();
    await userEvent.keyboard("{Escape}");
    expect(
      screen.queryByRole("complementary", { name: "Details" }),
    ).not.toBeInTheDocument();
  });

  it("says plainly when an article has gone", async () => {
    const api = fakeApi();
    const read = api.getEntity;
    api.getEntity = (b, d, c, id) =>
      id === "aldric"
        ? Promise.reject(new ChronosApiError(404, "Gone.", "NOT_FOUND"))
        : read(b, d, c, id);
    renderWorkspace("#/ember-pact/~issues", api);
    await userEvent.click(await screen.findByRole("button", { name: "aldric" }));
    const panel = await screen.findByRole("complementary", { name: "Details" });
    expect(
      await within(panel).findByText("This reference no longer exists in Akasha."),
    ).toBeInTheDocument();
  });
});

describe("scene facts from the graph", () => {
  it.each<[string, string[]]>([
    ["exchange", ["road", "shadow"]],
    ["sighting", ["tale"]],
    ["later", []],
  ])("threads through %s", (scene, expected) => {
    expect(threadsThrough(graph(), scene)).toEqual(expected);
  });

  it.each<[string, string[]]>([
    ["exchange", ["seal"]],
    ["coronation", ["crown"]],
    ["departs", []],
  ])("goals delivered at %s", (scene, expected) => {
    expect(goalsDeliveredAt(graph(), scene).map((g) => g.id)).toEqual(expected);
  });
});

describe("akashaArticleUrl", () => {
  it("points at the article's own route wherever Akasha is mounted", () => {
    expect(
      akashaArticleUrl("/", {
        database: "ember pact",
        collection: "characters",
        id: "aldric",
      }),
    ).toBe("/#/ember%20pact/characters/aldric");
  });
});
