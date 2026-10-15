// An in-memory `ChronosApi` for tests: the fixture book, kept in plain maps,
// with every call recorded. Writes change the maps, so a screen that saves and
// re-reads sees what it saved. `refuse` makes the next call to a method fail
// the way the server would, code and evidence included.

import type { ChronosApi } from "../api/ChronosApi";
import { ChronosApiError } from "../api/errors";
import type {
  Book,
  BookReport,
  EventWrite,
  EntityCandidate,
  Goal,
  Graph,
  LibraryCalendar,
  Plotline,
  PlotlinePreview,
  SceneEvent,
} from "../api/types";
import {
  ARTICLES,
  BOOK,
  CALENDARS,
  GOALS,
  SCENES,
  book as bookFixture,
  goalRef,
  graph as graphFixture,
  plotline as plotlineFixture,
  plotlineRows,
  report as reportFixture,
  summary,
} from "./fixtures";

export interface Call {
  method: string;
  args: unknown[];
}

export interface FakeApi extends ChronosApi {
  calls: Call[];
  books: Book[];
  scenes: Map<string, SceneEvent>;
  plotlines: Map<string, Plotline>;
  goals: Map<string, Goal>;
  calendars: LibraryCalendar[];
  reportValue: BookReport;
  graphValue: Graph;
  /** Make the next call to `method` fail with this status, message, code and evidence. */
  refuse: (
    method: keyof ChronosApi,
    status: number,
    code: string,
    evidence?: Record<string, unknown>,
  ) => void;
  /** The calls made to `method`, newest last. */
  callsTo: (method: keyof ChronosApi) => unknown[][];
}

/** What a scene write stores: nulls cleared, scheduled when it has a start. */
function sceneFields(body: EventWrite) {
  const scheduled = body.start_tick != null || body.start_date != null;
  return {
    location: body.location,
    characters: body.characters,
    items: body.items,
    description: body.description,
    start_tick: body.start_tick,
    end_tick: body.end_tick,
    title: body.title ?? undefined,
    scheduled,
  };
}

function notFound(what: string): never {
  throw new ChronosApiError(404, `No such ${what}.`, "NOT_FOUND");
}

export function fakeApi(): FakeApi {
  const refusals = new Map<string, ChronosApiError>();
  const calls: Call[] = [];
  const state = {
    books: [bookFixture()],
    scenes: new Map(SCENES.map((s) => [s.id, { ...s }])),
    plotlines: new Map(["road", "shadow", "tale"].map((id) => [id, plotlineFixture(id)])),
    goals: new Map(GOALS.map((g) => [g.id, { ...g }])),
    calendars: [...CALENDARS],
    reportValue: reportFixture(),
    graphValue: graphFixture(),
  };

  // Every method goes through here: recorded, then refused if a refusal is waiting.
  const record = <T>(method: string, args: unknown[], answer: () => T): Promise<T> => {
    calls.push({ method, args });
    const refusal = refusals.get(method);
    if (refusal) {
      refusals.delete(method);
      return Promise.reject(refusal);
    }
    try {
      return Promise.resolve(answer());
    } catch (e) {
      return Promise.reject(e);
    }
  };

  const findBook = (id: string) => state.books.find((b) => b.id === id) ?? notFound("book");

  const preview = (candidate: {
    id?: string;
    title?: string;
    events: string[];
    goals?: string[];
  }): PlotlinePreview => ({
    kind: "plotline-preview",
    id: candidate.id ?? "",
    title: candidate.title,
    events: candidate.events,
    goals: candidate.goals ?? [],
    goal_refs: (candidate.goals ?? []).map(goalRef),
    effective_events: candidate.events.map((e) => summary(e)),
    status: { conflicts: 0, ordering: { state: "ok" }, ends_at_terminus: { state: "ok" } },
  });

  const api: ChronosApi = {
    me: () => record("me", [], () => ({ username: "mara", role: "user" })),

    listBooks: () => record("listBooks", [], () => state.books),
    getBook: (b) => record("getBook", [b], () => findBook(b)),
    createBook: (b, body) =>
      record("createBook", [b, body], () => {
        if (state.books.some((x) => x.id === b)) {
          throw new ChronosApiError(409, "That id is taken.", "ALREADY_EXISTS");
        }
        const created: Book = {
          ...bookFixture(),
          ...body,
          id: b,
          plotlines: [],
          status: "consistent",
          rev: 1,
        };
        state.books.push(created);
        return created;
      }),
    updateBook: (b, body, rev) =>
      record("updateBook", [b, body, rev], () => {
        const current = findBook(b);
        const next = { ...current, ...body, rev: current.rev + 1 } as Book;
        state.books = state.books.map((x) => (x.id === b ? next : x));
        return next;
      }),
    deleteBook: (b, rev) =>
      record("deleteBook", [b, rev], () => {
        state.books = state.books.filter((x) => x.id !== b);
      }),
    setTerminus: (b, e) =>
      record("setTerminus", [b, e], () => {
        const next = { ...findBook(b), terminus: e };
        state.books = state.books.map((x) => (x.id === b ? next : x));
        return next;
      }),

    listPlotlines: (b, opts) =>
      record("listPlotlines", [b, opts], () => {
        const words = (opts?.filter ?? "").toLowerCase().split(/\s+/).filter(Boolean);
        const rows = plotlineRows().filter((r) =>
          words.every((w) => r.name.toLowerCase().includes(w)),
        );
        return {
          plotlines: rows,
          page: opts?.page ?? 1,
          pages: 1,
          per_page: opts?.perPage ?? 20,
          total: rows.length,
        };
      }),
    getPlotline: (b, p, opts) =>
      record(
        "getPlotline",
        [b, p, opts],
        () => state.plotlines.get(p) ?? notFound("plotline"),
      ),
    createPlotline: (b, p, body) =>
      record("createPlotline", [b, p, body], () => {
        const created = {
          ...plotlineFixture(p),
          ...preview({ id: p, ...body }),
          kind: "plotline" as const,
          book: BOOK,
          rev: 1,
        };
        state.plotlines.set(p, created as Plotline);
        return created as Plotline;
      }),
    updatePlotline: (b, p, body, rev) =>
      record("updatePlotline", [b, p, body, rev], () => {
        const current = state.plotlines.get(p) ?? notFound("plotline");
        const next = {
          ...current,
          ...body,
          effective_events: body.events.map((e) => summary(e)),
          rev: current.rev + 1,
        } as Plotline;
        state.plotlines.set(p, next);
        return next;
      }),
    deletePlotline: (b, p, rev, inline) =>
      record("deletePlotline", [b, p, rev, inline], () => {
        state.plotlines.delete(p);
      }),
    previewPlotline: (b, candidate, opts) =>
      record("previewPlotline", [b, candidate, opts], () => preview(candidate)),

    bookIssues: (b, opts) => record("bookIssues", [b, opts], () => state.reportValue),

    listEvents: (b, opts) =>
      record("listEvents", [b, opts], () => {
        const rows = [...state.scenes.values()].map((s) => ({
          id: s.id,
          book: BOOK,
          title: s.title ?? s.id,
          when: s.start_label ?? "unscheduled",
          scheduled: Boolean(s.scheduled),
          start_tick: s.start_tick,
          end_tick: s.end_tick,
          location: s.location.id,
          location_ref: s.location,
          plotlines: [...state.plotlines.values()]
            .filter((p) =>
              p.effective_events.some((e) => (typeof e === "string" ? e : e.id) === s.id),
            )
            .map((p) => p.id),
        }));
        return { events: rows, page: 1, pages: 1, per_page: 100, total: rows.length };
      }),
    timelineEvents: (b, opts) =>
      record("timelineEvents", [b, opts], () => {
        const rows = [...state.scenes.values()].map((s) => ({
          id: s.id,
          book: BOOK,
          title: s.title ?? s.id,
          when: s.start_label ?? "unscheduled",
          scheduled: Boolean(s.scheduled),
          start_tick: s.start_tick,
          end_tick: s.end_tick,
          start_label: s.start_label ?? null,
          end_label: s.end_label ?? null,
          start_parts: summary(s.id).start_parts ?? null,
          end_parts: summary(s.id).end_parts ?? null,
          location: s.location.id,
          location_ref: s.location,
          plotlines: Object.entries({
            road: ["departs", "exchange", "coronation"],
            shadow: ["infiltrates", "exchange", "coronation"],
            tale: ["sighting"],
          })
            .filter(([, path]) => path.includes(s.id))
            .map(([id]) => id),
        }));
        return {
          events: rows
            .filter((r) => r.scheduled)
            .sort((a, z) => (a.start_tick ?? 0) - (z.start_tick ?? 0)),
          unscheduled: rows.filter((r) => !r.scheduled),
          bounds: { start_tick: 24, end_tick: 240 },
          total: rows.length,
          plotlines: [...state.plotlines.values()].map((p) => ({
            id: p.id,
            title: p.title ?? p.id,
          })),
        };
      }),
    getEvent: (b, e, opts) =>
      record("getEvent", [b, e, opts], () => state.scenes.get(e) ?? notFound("scene")),
    createEvent: (b, e, body, opts) =>
      record("createEvent", [b, e, body, opts], () => {
        const created: SceneEvent = {
          kind: "event",
          id: e,
          book: BOOK,
          rev: 1,
          ...sceneFields(body),
        };
        state.scenes.set(e, created);
        return created;
      }),
    updateEvent: (b, e, body, rev, opts) =>
      record("updateEvent", [b, e, body, rev, opts], () => {
        const current = state.scenes.get(e) ?? notFound("scene");
        const next = { ...current, ...sceneFields(body), rev: current.rev + 1 };
        state.scenes.set(e, next);
        return next;
      }),
    deleteEvent: (b, e, rev, detach) =>
      record("deleteEvent", [b, e, rev, detach], () => {
        state.scenes.delete(e);
      }),

    listGoals: (b, opts) => record("listGoals", [b, opts], () => [...state.goals.values()]),
    getGoal: (b, g, opts) =>
      record("getGoal", [b, g, opts], () => state.goals.get(g) ?? notFound("goal")),
    createGoal: (b, g, body) =>
      record("createGoal", [b, g, body], () => {
        const created: Goal = {
          kind: "goal",
          id: g,
          book: BOOK,
          title: body.title ?? g,
          description: body.description,
          depends_on: body.depends_on ?? [],
          dependencies: (body.depends_on ?? []).map(goalRef),
          required_by: [],
          achieved_at: body.achieved_at ?? null,
          achieved_scene: null,
          plotlines: [],
          depth: 0,
          rev: 1,
          status: { state: "open", findings: [] },
        };
        state.goals.set(g, created);
        return created;
      }),
    updateGoal: (b, g, body, rev) =>
      record("updateGoal", [b, g, body, rev], () => {
        const current = state.goals.get(g) ?? notFound("goal");
        const next = { ...current, ...body, rev: current.rev + 1 } as Goal;
        state.goals.set(g, next);
        return next;
      }),
    deleteGoal: (b, g, rev, detach) =>
      record("deleteGoal", [b, g, rev, detach], () => {
        state.goals.delete(g);
      }),

    getGraph: (b, opts) => record("getGraph", [b, opts], () => state.graphValue),

    getEntity: (b, database, collection, id) =>
      record("getEntity", [b, database, collection, id], () => {
        const doc = ARTICLES[id];
        if (!doc) notFound("article");
        return { id, rev: 1, document: doc };
      }),
    searchEntities: (b, query) =>
      record("searchEntities", [b, query], () => {
        const collection = query.collection ?? "characters";
        const results: EntityCandidate[] = Object.entries(ARTICLES)
          .filter(([, doc]) =>
            doc.title.toLowerCase().includes((query.q ?? "").toLowerCase()),
          )
          .map(([id, doc]) => ({ database: BOOK, collection, id, title: doc.title }));
        return {
          database: BOOK,
          collection,
          collections: ["characters", "items", "locations"],
          results,
        };
      }),
    listWorlds: () =>
      record("listWorlds", [], () => [
        { database: BOOK, collections: ["characters", "items", "locations"] },
      ]),

    formatTicks: (b, ticks, opts) =>
      record("formatTicks", [b, ticks, opts], () =>
        ticks.map((tick) => ({
          tick,
          label: `Tick ${tick}`,
          parts: [`Tick ${tick}`],
          components: { hour: tick },
        })),
      ),
    resolveDates: (b, timeframe, opts) =>
      record("resolveDates", [b, timeframe, opts], () => ({
        start_tick: 24,
        end_tick: 48,
        ticks: [],
      })),

    listCalendars: () => record("listCalendars", [], () => state.calendars),
    createCalendar: (o, c, body) =>
      record("createCalendar", [o, c, body], () => {
        const created: LibraryCalendar = {
          kind: "calendar",
          id: c,
          owner: o,
          qualified_id: `${o}/${c}`,
          rev: 1,
          permissions: { write: true, delete: true },
          ...body,
        };
        state.calendars.push(created);
        return created;
      }),
    updateCalendar: (o, c, body, rev) =>
      record("updateCalendar", [o, c, body, rev], () => {
        const current =
          state.calendars.find((x) => x.owner === o && x.id === c) ?? notFound("calendar");
        const next = { ...current, ...body, rev: current.rev + 1 };
        state.calendars = state.calendars.map((x) => (x === current ? next : x));
        return next;
      }),
    deleteCalendar: (o, c, rev) =>
      record("deleteCalendar", [o, c, rev], () => {
        state.calendars = state.calendars.filter((x) => !(x.owner === o && x.id === c));
      }),
    shareCalendar: (o, c, username, role) =>
      record("shareCalendar", [o, c, username, role], () => undefined),
    unshareCalendar: (o, c, username) =>
      record("unshareCalendar", [o, c, username], () => undefined),
  };

  return Object.assign(state, api, {
    calls,
    refuse: (
      method: keyof ChronosApi,
      status: number,
      code: string,
      evidence: Record<string, unknown> = {},
    ) => {
      refusals.set(method, new ChronosApiError(status, `Refused: ${code}`, code, evidence));
    },
    callsTo: (method: keyof ChronosApi) =>
      calls.filter((c) => c.method === method).map((c) => c.args),
  }) as FakeApi;
}
