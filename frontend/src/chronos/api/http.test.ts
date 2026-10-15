import { vi } from "vitest";
import type { ChronosApi } from "./ChronosApi";
import { ChronosApiError, codeOf, evidenceIds, messageOf } from "./errors";
import { createHttpApi, queryString } from "./http";

const PL = { events: ["a", "b"] };
const SCENE = { location: { database: "w", collection: "locations", id: "x" } };

function recording(status = 200, body: unknown = {}) {
  const fetch = vi.fn(async (_url: string, _init?: RequestInit) => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })) as unknown as typeof window.fetch & ReturnType<typeof vi.fn>;
  return { api: createHttpApi({ base: "/timeline", fetch }), fetch };
}

describe("createHttpApi", () => {
  it.each<
    [string, (api: ChronosApi) => Promise<unknown>, string, string, unknown, string?]
  >([
    ["who is signed in", (a) => a.me(), "GET", "/timeline/auth/me", undefined],
    [
      "one book",
      (a) => a.getBook("ember pact"),
      "GET",
      "/timeline/books/ember%20pact",
      undefined,
    ],
    [
      "a book's replacement, guarded by its revision",
      (a) => a.updateBook("b", { title: "T" }, 3),
      "PUT",
      "/timeline/books/b",
      { title: "T" },
      "3",
    ],
    [
      "a book's deletion",
      (a) => a.deleteBook("b", 2),
      "DELETE",
      "/timeline/books/b",
      undefined,
      "2",
    ],
    [
      "the ending",
      (a) => a.setTerminus("b", "crowning"),
      "POST",
      "/timeline/books/b/terminus/crowning",
      undefined,
    ],
    [
      "a filtered, paged table",
      (a) => a.listPlotlines("b", { filter: "road", page: 2, perPage: 10 }),
      "GET",
      "/timeline/books/b/ui/plotlines?filter=road&page=2&per_page=10",
      undefined,
    ],
    [
      "a thread, expanded, through a chosen calendar",
      (a) => a.getPlotline("b", "p/1", { calendar: "earth" }),
      "GET",
      "/timeline/books/b/plotlines/p%2F1?expand=events&calendar=earth",
      undefined,
    ],
    [
      "a thread's save",
      (a) => a.updatePlotline("b", "p", PL, 5),
      "PUT",
      "/timeline/books/b/plotlines/p",
      PL,
      "5",
    ],
    [
      "a thread folded into its continuations",
      (a) => a.deletePlotline("b", "p", 5, true),
      "DELETE",
      "/timeline/books/b/plotlines/p?inline=true",
      undefined,
      "5",
    ],
    [
      "a preview",
      (a) => a.previewPlotline("b", { id: "p", ...PL }),
      "POST",
      "/timeline/books/b/ui/plotline-preview",
      { id: "p", ...PL },
    ],
    [
      "the report through the primary calendar",
      (a) => a.bookIssues("b"),
      "GET",
      "/timeline/books/b/ui/issues",
      undefined,
    ],
    [
      "a scene written in a calendar",
      (a) => a.createEvent("b", "s", SCENE, { calendar: "imperial" }),
      "POST",
      "/timeline/books/b/events/s?calendar=imperial",
      SCENE,
    ],
    [
      "a scene's deletion out of every thread",
      (a) => a.deleteEvent("b", "s", 1, true),
      "DELETE",
      "/timeline/books/b/events/s?detach=true",
      undefined,
      "1",
    ],
    [
      "a goal's deletion where it is in use",
      (a) => a.deleteGoal("b", "g", 4),
      "DELETE",
      "/timeline/books/b/goals/g",
      undefined,
      "4",
    ],
    [
      "an article read through Chronos",
      (a) => a.getEntity("b", "w", "characters", "aldric"),
      "GET",
      "/timeline/books/b/ui/entity/w/characters/aldric",
      undefined,
    ],
    [
      "a type-ahead",
      (a) => a.searchEntities("b", { q: "al", collection: "characters" }),
      "GET",
      "/timeline/books/b/ui/entities?q=al&collection=characters",
      undefined,
    ],
    [
      "dates resolved to ticks",
      (a) => a.resolveDates("b", { start_date: { year: 1 } }),
      "POST",
      "/timeline/books/b/ui/dates",
      { start_date: { year: 1 } },
    ],
    [
      "a calendar shared",
      (a) => a.shareCalendar("mara", "imperial", "ivo"),
      "PUT",
      "/timeline/calendars/mara/imperial/collaborators/ivo",
      { role: "reader" },
    ],
  ])("sends %s", async (_, act, method, url, body, ifMatch) => {
    const { api, fetch } = recording();
    await act(api);
    const [sentUrl, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(sentUrl).toBe(url);
    expect(init.method).toBe(method);
    expect(init.body === undefined ? undefined : JSON.parse(String(init.body))).toEqual(
      body,
    );
    expect((init.headers as Record<string, string>)["If-Match"]).toBe(ifMatch);
  });

  it.each<[string, (api: ChronosApi) => Promise<unknown>, unknown, unknown]>([
    ["books", (a) => a.listBooks(), { books: [{ id: "b" }] }, [{ id: "b" }]],
    ["goals", (a) => a.listGoals("b"), { goals: [{ id: "g" }] }, [{ id: "g" }]],
    ["calendars", (a) => a.listCalendars(), { calendars: [] }, []],
    ["worlds, when there are none", (a) => a.listWorlds(), {}, []],
    [
      "tick labels",
      (a) => a.formatTicks("b", [0, 24]),
      { ticks: [{ tick: 0 }] },
      [{ tick: 0 }],
    ],
  ])("unwraps the list of %s", async (_, act, payload, expected) => {
    const { api } = recording(200, payload);
    await expect(act(api)).resolves.toEqual(expected);
  });

  it("asks for each tick by name", async () => {
    const { api, fetch } = recording(200, { ticks: [] });
    await api.formatTicks("b", [0, 24], { calendar: "earth" });
    expect(fetch.mock.calls[0]?.[0]).toBe(
      "/timeline/books/b/ui/ticks?tick=0&tick=24&calendar=earth",
    );
  });

  it("turns a refusal into an error carrying its code and evidence", async () => {
    const { api } = recording(409, {
      error: "In use.",
      code: "PLOTLINE_IN_USE",
      evidence: { plotlines: ["a", 3, "b"] },
    });
    const error = await api.deletePlotline("b", "p", 1).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ChronosApiError);
    expect(messageOf(error)).toBe("In use.");
    expect(codeOf(error)).toBe("PLOTLINE_IN_USE");
    expect(evidenceIds(error, "plotlines")).toEqual(["a", "b"]);
    expect((error as ChronosApiError).isConflict).toBe(true);
  });

  it("says what status came back when the body says nothing", async () => {
    const { api } = recording(500, null);
    await expect(api.getBook("b")).rejects.toThrow("The server answered 500.");
  });
});

describe("queryString", () => {
  it.each<[string, [string, string | number | null | undefined][], string]>([
    ["nothing at all", [], ""],
    [
      "only empty values",
      [
        ["a", ""],
        ["b", null],
        ["c", undefined],
      ],
      "",
    ],
    ["a value with spaces", [["filter", "the road"]], "?filter=the+road"],
    [
      "repeats in order",
      [
        ["tick", 1],
        ["tick", 2],
      ],
      "?tick=1&tick=2",
    ],
  ])("writes %s", (_, params, expected) => {
    expect(queryString(params)).toBe(expected);
  });
});

describe("errors", () => {
  it.each<[unknown, string]>([
    [new Error("Boom."), "Boom."],
    ["not an error", "Something went wrong."],
    [new Error(""), "Something went wrong."],
  ])("messageOf(%s)", (error, expected) => {
    expect(messageOf(error)).toBe(expected);
  });

  it.each<[unknown, string | null]>([
    [new ChronosApiError(409, "x", "REVISION_CONFLICT"), "REVISION_CONFLICT"],
    [new Error("x"), null],
  ])("codeOf(%s)", (error, expected) => {
    expect(codeOf(error)).toBe(expected);
  });

  it("knows a stale revision when it sees one", () => {
    expect(new ChronosApiError(409, "x", "REVISION_CONFLICT").isStale).toBe(true);
    expect(new ChronosApiError(409, "x", "PLOTLINE_IN_USE").isStale).toBe(false);
  });
});
