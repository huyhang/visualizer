import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { QueryClient } from "@tanstack/react-query";
import { fakeApi, type FakeApi } from "../test/fakeApi";
import { renderWorkspace } from "../test/renderChronos";

interface Case {
  editor: string;
  hash: string;
  open: () => Promise<HTMLElement>;
  /** A collaborator saves the record while the dialog is open; the revision it had. */
  collaborate: (api: FakeApi) => number;
  /** What the writer changes before saving. */
  field: string;
  save: string;
  method: "updateGoal" | "updatePlotline" | "updateBook" | "updateEvent";
  /** Where the revision is among the method's arguments. */
  revArg: number;
}

/** Replace a record with a collaborator's newer save, answering the revision it replaced. */
function bump<T extends { rev: number }>(record: T | undefined, put: (next: T) => void) {
  if (!record) throw new Error("No such fixture.");
  put({ ...record, rev: record.rev + 1 });
  return record.rev;
}

const CASES: Case[] = [
  {
    editor: "goal",
    hash: "#/ember-pact/~goals/seal",
    open: async () => {
      await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
      return screen.findByRole("dialog", { name: /Edit “Deliver the Ember Seal”/ });
    },
    collaborate: (api) =>
      bump(api.goals.get("seal"), (next) => api.goals.set("seal", next)),
    field: "Name",
    save: "Save",
    method: "updateGoal",
    revArg: 3,
  },
  {
    editor: "thread",
    hash: "#/ember-pact/road",
    open: async () => {
      await userEvent.click(await screen.findByRole("button", { name: "Edit thread" }));
      const dialog = await screen.findByRole("dialog", { name: "Edit thread" });
      await within(dialog).findByRole("list", { name: "Scenes" });
      return dialog;
    },
    collaborate: (api) =>
      bump(api.plotlines.get("road"), (next) => api.plotlines.set("road", next)),
    field: "Name",
    save: "Save changes",
    method: "updatePlotline",
    revArg: 3,
  },
  {
    editor: "book",
    hash: "#/ember-pact",
    open: async () => {
      await userEvent.click(await screen.findByRole("button", { name: "Book settings" }));
      return screen.findByRole("dialog", { name: /Book settings/ });
    },
    collaborate: (api) => bump(api.books[0], (next) => (api.books = [next])),
    field: "Title",
    save: "Save changes",
    method: "updateBook",
    revArg: 2,
  },
  {
    editor: "scene",
    hash: "#/ember-pact/~scenes",
    open: async () => {
      await userEvent.click(await screen.findByRole("button", { name: "List" }));
      await userEvent.click(
        await screen.findByRole("button", { name: "Edit “Aldric Departs”" }),
      );
      return screen.findByRole("dialog", { name: "Edit “Aldric Departs”" });
    },
    collaborate: (api) =>
      bump(api.scenes.get("departs"), (next) => api.scenes.set("departs", next)),
    field: "Title",
    save: "Save scene",
    method: "updateEvent",
    revArg: 3,
  },
];

/** Everything on screen is read again, as when the tab regains focus. */
async function refetchEverything(client: QueryClient, api: FakeApi) {
  const before = api.calls.length;
  await client.invalidateQueries();
  await waitFor(() => expect(api.calls.length).toBeGreaterThan(before));
}

describe("an editor open while its record is read again", () => {
  it.each(CASES)(
    "keeps the $editor's draft and saves with the revision it opened at",
    async ({ hash, open, collaborate, field, save, method, revArg }) => {
      const api = fakeApi();
      const { client } = renderWorkspace(hash, api);
      const dialog = await open();
      const input = within(dialog).getByLabelText(field);
      await userEvent.clear(input);
      await userEvent.type(input, "Mine");

      const opened = collaborate(api);
      await refetchEverything(client, api);

      // Still the writer's draft, in the same form.
      expect(within(screen.getByRole("dialog")).getByLabelText(field)).toHaveValue("Mine");
      await userEvent.click(
        within(screen.getByRole("dialog")).getByRole("button", { name: save }),
      );
      await waitFor(() => expect(api.callsTo(method)).toHaveLength(1));
      // The revision it opened at, which the server refuses: the newer save survives.
      expect(api.callsTo(method)[0]?.[revArg]).toBe(opened);
      expect(await screen.findByRole("alert")).toHaveTextContent(/changed/i);
    },
  );
});
