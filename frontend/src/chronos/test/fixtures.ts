// A small book to test against: three threads, five scenes, three goals, a
// conflict and an undated scene -- enough for every screen to have something
// to say, and small enough to read in one go.

import type {
  Book,
  BookReport,
  EventSummary,
  Goal,
  Graph,
  LibraryCalendar,
  Plotline,
  PlotlineRow,
  SceneEvent,
} from "../api/types";

export const BOOK = "ember-pact";
const W = "ember-pact";
const loc = (id: string) => ({ database: W, collection: "locations", id });
const who = (id: string) => ({ database: W, collection: "characters", id });

const source = { owner: "mara", calendar: "imperial", rev: 1 };

export function book(overrides: Partial<Book> = {}): Book {
  return {
    kind: "book",
    id: BOOK,
    title: "The Ember Pact",
    overview: "A seal, a road and a crown.",
    terminus: "coronation",
    world: W,
    plotlines: ["road", "shadow", "tale"],
    status: "conflicted",
    rev: 2,
    permissions: { write: true, delete: true },
    calendars: [
      { id: "imperial", label: "Imperial Reckoning", source, primary: true },
      { id: "earth", label: "Earth", source: { ...source, calendar: "earth" } },
    ],
    ...overrides,
  };
}

const at = (day: number) => `Day ${day}`;

export function scene(
  id: string,
  title: string,
  day: number | null,
  overrides: Partial<SceneEvent> = {},
): SceneEvent {
  return {
    kind: "event",
    id,
    book: BOOK,
    title,
    location: loc("emberport"),
    start_tick: day === null ? null : day * 24,
    end_tick: day === null ? null : day * 24 + 24,
    start_label: day === null ? null : at(day),
    end_label: day === null ? null : at(day + 1),
    characters: [who("aldric")],
    items: [],
    description: `What happens in ${title}.`,
    scheduled: day !== null,
    rev: 1,
    ...overrides,
  };
}

export const SCENES: SceneEvent[] = [
  scene("departs", "Aldric Departs", 1, { location: loc("highkeep") }),
  scene("infiltrates", "Lyra Infiltrates", 1, { characters: [who("lyra")] }),
  scene("exchange", "The Harbor Exchange", 3, { characters: [who("aldric"), who("lyra")] }),
  scene("sighting", "Aldric Seen At Emberport", 1),
  scene("coronation", "The Coronation", 9, { location: loc("throne-hall") }),
  scene("later", "A Scene For Later", null, { characters: [who("lyra")] }),
];

export const PATHS: Record<string, string[]> = {
  road: ["departs", "exchange", "coronation"],
  shadow: ["infiltrates", "exchange", "coronation"],
  tale: ["sighting"],
};

const TITLES: Record<string, string> = {
  road: "The Knight's Road",
  shadow: "The Spy's Shadow",
  tale: "The Witness's Tale",
};

export function summary(sceneId: string, extra: Partial<EventSummary> = {}): EventSummary {
  const s = SCENES.find((e) => e.id === sceneId) ?? scene(sceneId, sceneId, null);
  return {
    id: s.id,
    title: s.title,
    start_tick: s.start_tick,
    end_tick: s.end_tick,
    start_label: s.start_label,
    end_label: s.end_label,
    start_parts: s.start_label ? ["Year 1", "Month 1", s.start_label, "00:00 AF"] : null,
    end_parts: s.end_label ? ["Year 1", "Month 1", s.end_label, "00:00 AF"] : null,
    location: s.location,
    characters: s.characters,
    items: s.items,
    description_preview: s.description,
    scheduled: s.scheduled,
    findings: [],
    owned: true,
    is_terminus: s.id === "coronation",
    is_convergence: s.id === "exchange",
    ...extra,
  };
}

export const GOALS: Goal[] = [
  {
    kind: "goal",
    id: "seal",
    book: BOOK,
    title: "Deliver the Ember Seal",
    description: "The seal reaches the harbor.",
    depends_on: [],
    dependencies: [],
    required_by: [{ id: "crown", title: "See the crown pressed", achieved: true }],
    achieved_at: "exchange",
    achieved_scene: { id: "exchange", title: "The Harbor Exchange", when: "Day 3 → Day 4" },
    plotlines: [{ id: "road", title: TITLES.road ?? "" }],
    depth: 0,
    rev: 1,
    status: { state: "achieved", findings: [] },
  },
  {
    kind: "goal",
    id: "crown",
    book: BOOK,
    title: "See the crown pressed",
    depends_on: ["seal"],
    dependencies: [{ id: "seal", title: "Deliver the Ember Seal", achieved: true }],
    required_by: [],
    achieved_at: "coronation",
    achieved_scene: { id: "coronation", title: "The Coronation", when: "Day 9 → Day 10" },
    plotlines: [{ id: "shadow", title: TITLES.shadow ?? "" }],
    depth: 1,
    rev: 1,
    status: { state: "achieved", findings: [] },
  },
  {
    kind: "goal",
    id: "where",
    book: BOOK,
    title: "Establish who was where",
    depends_on: [],
    dependencies: [],
    required_by: [],
    achieved_at: null,
    achieved_scene: null,
    plotlines: [{ id: "tale", title: TITLES.tale ?? "" }],
    depth: 0,
    rev: 1,
    status: {
      state: "open",
      findings: [
        {
          code: "GOAL_UNACHIEVED",
          severity: "info",
          message: "No scene achieves this goal yet.",
        },
      ],
    },
  },
];

const GOALS_OF: Record<string, string[]> = {
  road: ["seal"],
  shadow: ["crown"],
  tale: ["where"],
};

export function goalRef(id: string) {
  const g = GOALS.find((x) => x.id === id);
  return {
    id,
    title: g?.title ?? id,
    achieved: g?.status.state === "achieved",
    missing: !g,
    achieved_at: g?.achieved_at ?? null,
    achieved_scene: g?.achieved_scene ?? null,
  };
}

const CONFLICT = {
  code: "TEMPORAL_CONFLICT",
  severity: "conflict" as const,
  message: "'aldric' cannot be here and in 'Aldric Seen At Emberport' at once.",
  events: ["sighting"],
  refs: [who("aldric")],
};

export function plotline(id: string): Plotline {
  const path = PATHS[id] ?? [];
  return {
    kind: "plotline",
    id,
    book: BOOK,
    title: TITLES[id] ?? id,
    overview: "",
    events: id === "tale" ? path : path.slice(0, 1),
    goals: GOALS_OF[id] ?? [],
    goal_refs: (GOALS_OF[id] ?? []).map(goalRef),
    continues_into: null,
    effective_events: path.map((e) =>
      summary(e, e === "departs" ? { findings: [CONFLICT] } : {}),
    ),
    status: {
      conflicts: id === "road" ? 1 : id === "tale" ? 2 : 0,
      ordering: { state: "ok" },
      ends_at_terminus:
        id === "tale" ? { state: "conflicted", message: "Stops early." } : { state: "ok" },
      continuation: { state: "ok" },
    },
    rev: 1,
  };
}

export function plotlineRows(): PlotlineRow[] {
  return Object.keys(PATHS).map((id) => ({
    id,
    book: BOOK,
    name: TITLES[id] ?? id,
    overview: id === "road" ? "Aldric carries the seal." : "",
    conflicts: plotline(id).status.conflicts ?? 0,
    goals: (GOALS_OF[id] ?? []).map(goalRef),
  }));
}

export function graph(): Graph {
  const edges = Object.entries(PATHS).flatMap(([pl, path]) =>
    path.slice(1).map((to, n) => ({ from: path[n] ?? "", to, plotlines: [pl] })),
  );
  return {
    nodes: SCENES.filter((s) => s.id !== "later").map((s) => {
      const e = summary(s.id);
      return {
        id: e.id,
        title: e.title,
        start_tick: e.start_tick,
        end_tick: e.end_tick,
        start_label: e.start_label,
        end_label: e.end_label,
        start_parts: e.start_parts,
        end_parts: e.end_parts,
        scheduled: e.scheduled,
        is_terminus: e.is_terminus,
        is_convergence: e.is_convergence,
        is_divergence: false,
      };
    }),
    edges,
    convergence: ["exchange"],
    divergence: [],
    terminus: "coronation",
    plotlines: Object.keys(PATHS).map((id) => ({
      id,
      title: TITLES[id],
      events: plotline(id).events,
      effective_events: PATHS[id] ?? [],
      goals: GOALS_OF[id],
      continues_into: null,
    })),
    goals: GOALS.map((g) => goalRef(g.id)),
  };
}

export function report(): BookReport {
  return {
    status: "conflicted",
    summary: { problems: 2, notes: 2, unscheduled: 1 },
    problems: [
      {
        title: "A character in two places at once",
        severity: "conflict",
        codes: ["TEMPORAL_CONFLICT"],
        issues: [
          {
            code: "TEMPORAL_CONFLICT",
            severity: "conflict",
            message: CONFLICT.message,
            scene: { id: "departs", title: "Aldric Departs" },
            events: [{ id: "sighting", title: "Aldric Seen At Emberport" }],
            plotlines: [
              { id: "road", title: TITLES.road ?? "" },
              { id: "tale", title: TITLES.tale ?? "" },
            ],
            refs: [who("aldric")],
            goal: null,
            goals: [],
          },
        ],
      },
      {
        title: "Threads that do not reach the ending",
        severity: "conflict",
        codes: ["TERMINUS_VIOLATION"],
        issues: [
          {
            code: "TERMINUS_VIOLATION",
            severity: "conflict",
            message: "This plotline stops at 'Aldric Seen At Emberport'.",
            scene: { id: "sighting", title: "Aldric Seen At Emberport" },
            events: [],
            plotlines: [{ id: "tale", title: TITLES.tale ?? "" }],
            refs: [],
            goal: null,
            goals: [],
          },
        ],
      },
    ],
    notes: [
      {
        title: "Goals still waiting for a scene",
        severity: "info",
        codes: ["GOAL_UNACHIEVED"],
        issues: [
          {
            code: "GOAL_UNACHIEVED",
            severity: "info",
            message: "No scene achieves this goal yet.",
            scene: null,
            events: [],
            plotlines: [],
            refs: [],
            goal: { id: "where", title: "Establish who was where" },
            goals: [],
          },
        ],
      },
      {
        title: "Scenes still waiting for a time",
        severity: "info",
        codes: ["UNSCHEDULED"],
        issues: [
          {
            code: "UNSCHEDULED",
            severity: "info",
            message: "This scene has no time yet.",
            scene: { id: "later", title: "A Scene For Later" },
            events: [],
            plotlines: [],
            refs: [],
            goal: null,
            goals: [],
          },
        ],
      },
    ],
    plotlines: [
      { id: "road", title: TITLES.road, problems: 1 },
      { id: "shadow", title: TITLES.shadow, problems: 0 },
      { id: "tale", title: TITLES.tale, problems: 2 },
    ],
  };
}

export const ARTICLES: Record<string, { title: string; [k: string]: unknown }> = {
  aldric: {
    title: "Sir Aldric",
    role: "Knight",
    body: "Sworn to [[locations/highkeep|Highkeep]].",
  },
  lyra: { title: "Lyra", role: "Spy" },
  emberport: { title: "Emberport" },
  highkeep: { title: "Highkeep" },
  "throne-hall": { title: "The Throne Hall" },
};

export const CALENDARS: LibraryCalendar[] = [
  {
    kind: "calendar",
    id: "imperial",
    owner: "mara",
    qualified_id: "mara/imperial",
    name: "Imperial Reckoning",
    descriptor: {
      base_unit: "hour",
      cycles: [
        { name: "day", size: 24 },
        { name: "month", size: 30 },
        { name: "year", size: 12 },
      ],
      epoch_label: "AF",
    },
    notes: "Kept in the capital.",
    permissions: { write: true, delete: true },
    rev: 1,
  },
];
