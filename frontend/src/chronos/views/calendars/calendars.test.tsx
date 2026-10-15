import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fakeApi } from "../../test/fakeApi";
import { renderWorkspace } from "../../test/renderChronos";

describe("the calendar library", () => {
  it("shows each calendar with how it counts", async () => {
    renderWorkspace("#/~calendars");
    const card = (
      await screen.findByRole("heading", { name: "Imperial Reckoning" })
    ).closest("article") as HTMLElement;
    expect(within(card).getByText("mara/imperial")).toBeInTheDocument();
    expect(within(card).getByText("Yours")).toBeInTheDocument();
    expect(
      within(card).getByText(/Ticks are hours: 24 hours to a day/),
    ).toBeInTheDocument();
  });

  it("creates a calendar in the writer's own library, its id following the name", async () => {
    const { api } = renderWorkspace("#/~calendars");
    await userEvent.click(await screen.findByRole("button", { name: "New calendar" }));
    await userEvent.type(screen.getByLabelText("Name"), "Elvish Count");
    expect(screen.getByLabelText("Id")).toHaveValue("elvish-count");
    await userEvent.click(screen.getByRole("button", { name: "Create calendar" }));
    await waitFor(() => expect(api.callsTo("createCalendar")).toHaveLength(1));
    expect(api.callsTo("createCalendar")[0]).toEqual([
      "mara",
      "elvish-count",
      {
        name: "Elvish Count",
        notes: "",
        descriptor: {
          base_unit: "hour",
          epoch_label: "",
          cycles: [
            { name: "day", size: 24 },
            { name: "month", size: 30 },
            { name: "year", size: 12 },
          ],
        },
      },
    ]);
  });

  it("says so, in the form, when the id is already taken", async () => {
    const api = fakeApi();
    api.refuse("createCalendar", 409, "ALREADY_EXISTS");
    renderWorkspace("#/~calendars", api);
    await userEvent.click(await screen.findByRole("button", { name: "New calendar" }));
    await userEvent.type(screen.getByLabelText("Name"), "Imperial");
    await userEvent.click(screen.getByRole("button", { name: "Create calendar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You already have a calendar with the id “imperial”.",
    );
  });

  it("edits a calendar with the revision it read", async () => {
    const { api } = renderWorkspace("#/~calendars");
    await userEvent.click(
      await screen.findByRole("button", { name: "Edit this calendar" }),
    );
    expect(screen.getByLabelText("Id")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.callsTo("updateCalendar")).toHaveLength(1));
    const [owner, id, body, rev] = api.callsTo("updateCalendar")[0] as [
      string,
      string,
      { name: string },
      number,
    ];
    expect([owner, id, body.name, rev]).toEqual([
      "mara",
      "imperial",
      "Imperial Reckoning",
      1,
    ]);
  });

  it("deletes a calendar only once confirmed", async () => {
    const { api } = renderWorkspace("#/~calendars");
    await userEvent.click(
      await screen.findByRole("button", { name: "Delete this calendar" }),
    );
    expect(screen.getByText(/Books that already use it keep working/)).toBeInTheDocument();
    expect(api.callsTo("deleteCalendar")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(api.callsTo("deleteCalendar")).toEqual([["mara", "imperial", 1]]),
    );
  });

  it("shares a calendar with another writer", async () => {
    const { api } = renderWorkspace("#/~calendars");
    await userEvent.click(
      await screen.findByRole("button", { name: "Share this calendar" }),
    );
    await userEvent.type(screen.getByLabelText("Writer"), "ivo");
    await userEvent.click(screen.getByRole("button", { name: "Share" }));
    await waitFor(() =>
      expect(api.callsTo("shareCalendar")).toEqual([["mara", "imperial", "ivo", "reader"]]),
    );
  });

  it("offers no tools on a calendar someone else shared", async () => {
    const api = fakeApi();
    api.calendars = [{ ...api.calendars[0]!, owner: "ivo", qualified_id: "ivo/imperial" }];
    renderWorkspace("#/~calendars", api);
    expect(await screen.findByText("Shared by ivo")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Edit this calendar" }),
    ).not.toBeInTheDocument();
  });
});
