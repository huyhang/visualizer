import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fakeApi } from "../../test/fakeApi";
import { renderWorkspace } from "../../test/renderChronos";

async function openEditor(hash = "#/ember-pact/~goals/seal", api = fakeApi()) {
  const view = renderWorkspace(hash, api);
  await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
  return {
    ...view,
    dialog: await screen.findByRole("dialog", { name: /Edit “Deliver the Ember Seal”/ }),
  };
}

describe("the goal editor", () => {
  it("writes a new goal at an id that follows its name", async () => {
    const { api } = renderWorkspace("#/ember-pact/~goals");
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "New goal" }))[0] as HTMLElement,
    );
    const dialog = await screen.findByRole("dialog", { name: "New goal" });
    await userEvent.type(within(dialog).getByLabelText("Name"), "Harbor Watch");
    expect(within(dialog).getByLabelText("Id")).toHaveValue("harbor-watch");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create goal" }));
    await vi.waitFor(() => expect(api.callsTo("createGoal")).toHaveLength(1));
    expect(api.callsTo("createGoal")[0]).toEqual([
      "ember-pact",
      "harbor-watch",
      { title: "Harbor Watch", description: "", depends_on: [], achieved_at: null },
    ]);
  });

  it("refuses an id already taken before asking the server", async () => {
    renderWorkspace("#/ember-pact/~goals");
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "New goal" }))[0] as HTMLElement,
    );
    const dialog = await screen.findByRole("dialog", { name: "New goal" });
    await userEvent.type(within(dialog).getByLabelText("Name"), "Seal");
    expect(
      within(dialog).getByText("That id is already taken in this book."),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Create goal" })).toBeDisabled();
  });

  it("saves with the revision it read", async () => {
    const { api, dialog } = await openEditor();
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(api.callsTo("updateGoal")).toHaveLength(1));
    expect(api.callsTo("updateGoal")[0]?.[3]).toBe(1);
  });

  it("says which goals a loop would run through", async () => {
    const api = fakeApi();
    api.refuse("updateGoal", 400, "GOAL_CYCLE", { cycle: ["seal", "crown", "seal"] });
    const { dialog } = await openEditor(undefined, api);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "That would make the goals loop: seal → crown → seal.",
    );
  });

  it("explains a save that raced a collaborator", async () => {
    const api = fakeApi();
    api.refuse("updateGoal", 409, "REVISION_CONFLICT");
    const { dialog } = await openEditor(undefined, api);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      /Someone else changed this goal/,
    );
  });
});

describe("deleting a goal", () => {
  it("names what points at it and detaches it from them", async () => {
    const { api } = renderWorkspace("#/ember-pact/~goals/seal");
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog", {
      name: /Delete “Deliver the Ember Seal”/,
    });
    expect(within(dialog).getByText("The Knight's Road")).toBeInTheDocument();
    expect(within(dialog).getByText("See the crown pressed")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete anyway" }));
    await vi.waitFor(() => expect(api.callsTo("deleteGoal")).toHaveLength(1));
    expect(api.callsTo("deleteGoal")[0]).toEqual(["ember-pact", "seal", 1, true]);
  });

  it("takes the server's word when the page was stale, then offers to detach", async () => {
    const api = fakeApi();
    const where = api.goals.get("where");
    if (where) api.goals.set("where", { ...where, plotlines: [] });
    api.refuse("deleteGoal", 409, "GOAL_IN_USE", { plotlines: ["tale"], goals: [] });
    renderWorkspace("#/ember-pact/~goals/where", api);
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog", {
      name: /Delete “Establish who was where”/,
    });
    expect(within(dialog).getByText("Nothing points at it.")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(await within(dialog).findByText("The Witness's Tale")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete anyway" }));
    await vi.waitFor(() => expect(api.callsTo("deleteGoal")).toHaveLength(2));
    expect(api.callsTo("deleteGoal").map((args) => args[3])).toEqual([false, true]);
  });
});
