import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CalendarDescriptor } from "../../api/types";
import { fakeApi, type FakeApi } from "../../test/fakeApi";
import { renderWorkspace } from "../../test/renderChronos";
import { saveProblem } from "./SceneEditor";
import { ChronosApiError } from "../../api/errors";

const IMPERIAL: CalendarDescriptor = {
  base_unit: "hour",
  cycles: [
    { name: "day", size: 24 },
    { name: "month", size: 30 },
    { name: "year", size: 12 },
  ],
  epoch_label: "AF",
};

/** The fixture book, its primary calendar given a descriptor so its scenes can be dated. */
function datedApi(): FakeApi {
  const api = fakeApi();
  const calendar = api.books[0]?.calendars?.[0];
  if (calendar) calendar.descriptor = IMPERIAL;
  return api;
}

async function openNewScene(api: FakeApi) {
  renderWorkspace("#/ember-pact/~scenes", api);
  await userEvent.click(await screen.findByRole("button", { name: "New scene" }));
  return screen.findByRole("dialog", { name: "Write a new scene" });
}

async function choose(dialog: HTMLElement, field: string, typed: string, option: string) {
  await userEvent.type(
    within(dialog).getByRole("combobox", { name: `Search for ${field}` }),
    typed,
  );
  await userEvent.click(
    await within(dialog).findByRole("option", { name: new RegExp(option) }),
  );
}

describe("writing a new scene", () => {
  it("creates it at the id its title gives, with its place, cast and dates", async () => {
    const api = datedApi();
    const dialog = await openNewScene(api);
    await userEvent.type(within(dialog).getByLabelText("Title"), "The Night Market");
    expect(within(dialog).getByLabelText("Id")).toHaveValue("the-night-market");
    await choose(dialog, "place", "Ember", "Emberport");
    await choose(dialog, "characters", "Aldric", "Sir Aldric");
    const starts = within(dialog).getByRole("group", { name: "Starts" });
    const ends = within(dialog).getByRole("group", { name: "Ends" });
    for (const [group, day] of [
      [starts, "3"],
      [ends, "4"],
    ] as const) {
      await userEvent.type(within(group).getByLabelText("Year"), "1");
      await userEvent.type(within(group).getByLabelText("Month"), "1");
      await userEvent.type(within(group).getByLabelText("Day"), day);
    }
    await userEvent.click(within(dialog).getByRole("button", { name: "Create scene" }));

    await waitFor(() => expect(api.callsTo("createEvent")).toHaveLength(1));
    const [book, id, body, options] = api.callsTo("createEvent")[0] as [
      string,
      string,
      Record<string, unknown>,
      unknown,
    ];
    expect([book, id]).toEqual(["ember-pact", "the-night-market"]);
    expect(body).toMatchObject({
      title: "The Night Market",
      location: { database: "ember-pact", collection: "locations", id: "emberport" },
      characters: [{ database: "ember-pact", collection: "characters", id: "aldric" }],
      start_date: { year: 1, month: 1, day: 3 },
      end_date: { year: 1, month: 1, day: 4 },
    });
    expect(options).toEqual({ calendar: "imperial" });
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Write a new scene" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("asks for a place before anything is sent", async () => {
    const api = datedApi();
    const dialog = await openNewScene(api);
    await userEvent.type(within(dialog).getByLabelText("Title"), "Nowhere");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create scene" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Choose where this scene happens.",
    );
    expect(api.callsTo("createEvent")).toEqual([]);
  });

  it("takes the next free id when the title's is taken", async () => {
    const api = datedApi();
    api.refuse("createEvent", 409, "ALREADY_EXISTS");
    const dialog = await openNewScene(api);
    await userEvent.type(within(dialog).getByLabelText("Title"), "Dawn");
    await choose(dialog, "place", "High", "Highkeep");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create scene" }));
    await waitFor(() =>
      expect(api.callsTo("createEvent").map((c) => c[1])).toEqual(["dawn", "dawn-2"]),
    );
  });

  it("refuses half a timeframe in the form's own words", async () => {
    const api = datedApi();
    const dialog = await openNewScene(api);
    await choose(dialog, "place", "Ember", "Emberport");
    await userEvent.type(
      within(within(dialog).getByRole("group", { name: "Starts" })).getByLabelText("Year"),
      "1",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Create scene" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Give both dates, or neither",
    );
    expect(api.callsTo("createEvent")).toEqual([]);
  });
});

describe("the timing section", () => {
  it("carries typed dates across to ticks, resolved by the server", async () => {
    const api = datedApi();
    const dialog = await openNewScene(api);
    for (const name of ["Starts", "Ends"]) {
      await userEvent.type(
        within(within(dialog).getByRole("group", { name })).getByLabelText("Year"),
        "1",
      );
    }
    await userEvent.click(within(dialog).getByRole("radio", { name: "Tick" }));
    expect(await within(dialog).findByDisplayValue("24")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Ends at (tick)")).toHaveValue("48");
    expect(api.callsTo("resolveDates").at(-1)).toEqual([
      "ember-pact",
      { start_date: { year: 1 }, end_date: { year: 1 } },
      { calendar: "imperial" },
    ]);
  });

  it("keeps ticks typed while the dates were still being read", async () => {
    const api = datedApi();
    let answer: () => void = () => {};
    const resolve = api.resolveDates;
    api.resolveDates = (...args) =>
      new Promise((done) => {
        answer = () => done(resolve(...args));
      });
    const dialog = await openNewScene(api);
    for (const name of ["Starts", "Ends"]) {
      await userEvent.type(
        within(within(dialog).getByRole("group", { name })).getByLabelText("Year"),
        "1",
      );
    }
    await userEvent.click(within(dialog).getByRole("radio", { name: "Tick" }));
    const end = within(dialog).getByLabelText("Ends at (tick)");
    await userEvent.clear(end);
    await userEvent.type(end, "99");
    await act(async () => answer());
    expect(end).toHaveValue("99");
  });

  it("saves the scene's own ticks if Save comes before its dates are read", async () => {
    const api = datedApi();
    api.formatTicks = () => new Promise(() => {});
    renderWorkspace("#/ember-pact/~scenes", api);
    await userEvent.click(await screen.findByRole("button", { name: "List" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Edit “Aldric Departs”" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Edit “Aldric Departs”" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save scene" }));
    await waitFor(() => expect(api.callsTo("updateEvent")).toHaveLength(1));
    expect(api.callsTo("updateEvent")[0]?.[2]).toMatchObject({
      start_tick: 24,
      end_tick: 48,
    });
  });

  it("offers only ticks to a book whose calendar cannot be written in", async () => {
    const dialog = await openNewScene(fakeApi());
    expect(within(dialog).queryByRole("radio", { name: "Date" })).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText("Starts at (tick)")).toBeInTheDocument();
  });
});

describe("editing a scene", () => {
  it("reads the scene afresh and saves with its revision, keeping its ticks", async () => {
    const api = fakeApi();
    renderWorkspace("#/ember-pact/~scenes", api);
    await userEvent.click(await screen.findByRole("button", { name: "List" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Edit “Aldric Departs”" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Edit “Aldric Departs”" });
    expect(within(dialog).getByLabelText("Id")).toBeDisabled();
    const title = within(dialog).getByLabelText("Title");
    await userEvent.clear(title);
    await userEvent.type(title, "Aldric Rides Out");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save scene" }));
    await waitFor(() => expect(api.callsTo("updateEvent")).toHaveLength(1));
    const [, id, body, rev] = api.callsTo("updateEvent")[0] as [
      string,
      string,
      Record<string, unknown>,
      number,
    ];
    expect([id, rev]).toEqual(["departs", 1]);
    expect(body).toMatchObject({
      title: "Aldric Rides Out",
      start_tick: 24,
      end_tick: 48,
      location: { id: "highkeep" },
    });
  });

  it("names whoever a remove button takes off the scene", async () => {
    renderWorkspace("#/ember-pact/~scenes");
    await userEvent.click(await screen.findByRole("button", { name: "List" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Edit “Aldric Departs”" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Edit “Aldric Departs”" });
    expect(
      await within(dialog).findByRole("button", { name: "Remove Sir Aldric" }),
    ).toBeInTheDocument();
  });

  it("opens from the scene's panel too", async () => {
    renderWorkspace("#/ember-pact/~scenes");
    await userEvent.click(await screen.findByRole("button", { name: "List" }));
    await userEvent.click(await screen.findByRole("button", { name: "Lyra Infiltrates" }));
    const panel = await screen.findByRole("complementary", { name: "Details" });
    await userEvent.click(await within(panel).findByRole("button", { name: "Edit scene" }));
    expect(
      await screen.findByRole("dialog", { name: "Edit “Lyra Infiltrates”" }),
    ).toBeInTheDocument();
  });
});

describe("saveProblem", () => {
  it.each<[unknown, RegExp]>([
    [new ChronosApiError(409, "Stale.", "REVISION_CONFLICT"), /changed elsewhere/],
    [
      new ChronosApiError(
        400,
        "That timeframe ends before it begins.",
        "INVALID_TIMEFRAME",
      ),
      /ends before it begins/,
    ],
    ["nonsense", /Could not save the scene/],
  ])("words %s", (error, expected) => {
    expect(saveProblem(error)).toMatch(expected);
  });
});
