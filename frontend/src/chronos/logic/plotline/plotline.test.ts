import type {
  EventFinding,
  EventSummary,
  Plotline,
  PlotlinePreview,
  PlotlineStatus,
} from "../../api/types";
import { better, headline, movedPositions, summarize, type OrderSummary } from "./compare";
import {
  bodyOf,
  candidateKey,
  candidateOf,
  continueInto,
  draftFrom,
  draftProblems,
  emptyDraft,
  sameDraft,
  type ThreadDraft,
} from "./draft";
import { focusLabel, isHidden } from "./focus";
import { sections } from "./sections";
import { byTime, dropIndex, insertAt, keyMove, move, removeAt, type Timing } from "./order";
import {
  conflictCount,
  markerOf,
  meetCount,
  meetHint,
  problemScenes,
  roleOf,
  verdictNotes,
} from "./verdicts";

const finding = (severity: "conflict" | "info"): EventFinding => ({
  code: "X",
  severity,
  message: severity,
  events: [],
  refs: [],
});
const scene = (id: string, extra: Partial<EventSummary> = {}): EventSummary => ({
  id,
  title: id.toUpperCase(),
  ...extra,
});

describe("order", () => {
  it.each<[number, number, string[]]>([
    [0, 2, ["b", "c", "a"]],
    [2, 0, ["c", "a", "b"]],
    [1, 1, ["a", "b", "c"]],
    [0, 3, ["a", "b", "c"]],
    [-1, 0, ["a", "b", "c"]],
  ])("move from %i to %i", (from, to, expected) => {
    expect(move(["a", "b", "c"], from, to)).toEqual(expected);
  });

  it.each<[number, number, boolean, number]>([
    [0, 2, false, 1],
    [0, 2, true, 2],
    [3, 1, false, 1],
    [3, 1, true, 2],
  ])(
    "dropping row %i on row %i (below midpoint: %s) lands at %i",
    (from, index, below, expected) => {
      expect(dropIndex(from, index, below)).toBe(expected);
    },
  );

  it.each<[number | undefined, string[]]>([
    [undefined, ["a", "b", "x"]],
    [0, ["x", "a", "b"]],
    [1, ["a", "x", "b"]],
    [99, ["a", "b", "x"]],
  ])("insertAt %s", (at, expected) => {
    expect(insertAt(["a", "b"], "x", at)).toEqual(expected);
  });

  it("removes by position", () => {
    expect(removeAt(["a", "b", "a"], 2)).toEqual(["a", "b"]);
  });

  it("sorts dated scenes by start and keeps undated ones after, in order", () => {
    const timing: Record<string, Timing> = {
      late: { scheduled: true, start_tick: 90 },
      early: { scheduled: true, start_tick: 10 },
      undated1: { scheduled: false },
      undated2: {},
    };
    expect(byTime(["undated1", "late", "undated2", "early"], (id) => timing[id])).toEqual([
      "early",
      "late",
      "undated1",
      "undated2",
    ]);
  });

  it.each<[string, number, number, number | null]>([
    ["ArrowUp", 2, 3, 1],
    ["ArrowDown", 0, 3, 1],
    ["ArrowUp", 0, 3, null],
    ["ArrowDown", 2, 3, null],
    ["Enter", 1, 3, null],
  ])("%s from %i of %i", (key, index, length, expected) => {
    expect(keyMove(key, index, length)).toBe(expected);
  });
});

const PLOTLINE: Plotline = {
  kind: "plotline",
  id: "road",
  book: "b",
  title: "The Road",
  overview: "Notes.",
  events: ["a", "b"],
  goals: ["seal"],
  continues_into: "trunk",
  continues_into_title: "The Trunk",
  continues_into_at: "c",
  effective_events: [],
  status: {},
  rev: 4,
};

describe("draft", () => {
  it("reads a thread into a draft and back into what a save sends", () => {
    const draft = draftFrom(PLOTLINE);
    expect(draft).toEqual({
      id: "road",
      title: "The Road",
      overview: "Notes.",
      goals: ["seal"],
      events: ["a", "b"],
      continuesInto: "trunk",
      continuesIntoTitle: "The Trunk",
      continuesIntoAt: "c",
    });
    expect(bodyOf(draft)).toEqual({
      title: "The Road",
      overview: "Notes.",
      events: ["a", "b"],
      goals: ["seal"],
      continues_into: "trunk",
      continues_into_at: "c",
    });
  });

  it("sends no title when there is none, and always the overview", () => {
    expect(bodyOf({ ...emptyDraft(), title: "  ", events: ["a"] })).toMatchObject({
      title: undefined,
      overview: "",
    });
  });

  it("previews a candidate order without changing the draft", () => {
    const draft = draftFrom(PLOTLINE);
    expect(candidateOf(draft, ["b", "a"])).toMatchObject({
      id: "road",
      events: ["b", "a"],
    });
    expect(candidateOf({ ...draft, id: "" }).id).toBeUndefined();
  });

  it("re-judges for what changes a verdict, not for a new title", () => {
    const draft = draftFrom(PLOTLINE);
    expect(candidateKey({ ...draft, title: "Other" })).toBe(candidateKey(draft));
    expect(candidateKey({ ...draft, events: ["b", "a"] })).not.toBe(candidateKey(draft));
    expect(candidateKey(draft, ["b", "a"])).toBe(
      candidateKey({ ...draft, events: ["b", "a"] }),
    );
  });

  it.each<[string, ThreadDraft, boolean, string[], string[]]>([
    ["a sound new thread", { ...emptyDraft(), id: "road", events: ["a"] }, true, [], []],
    [
      "a new thread with no id or scenes",
      emptyDraft(),
      true,
      [],
      ["Give it a name or an id.", "A thread needs at least one scene of its own."],
    ],
    [
      "a taken id",
      { ...emptyDraft(), id: "road", events: ["a"] },
      true,
      ["road"],
      ["That id is already taken in this book."],
    ],
    [
      "an existing thread keeps its id unchecked",
      { ...emptyDraft(), id: "Road", events: ["a"] },
      false,
      [],
      [],
    ],
  ])("problems of %s", (_, draft, creating, taken, expected) => {
    expect(draftProblems(draft, creating, taken)).toEqual(expected);
  });

  it("drops the join scene when the continuation changes", () => {
    const next = continueInto(draftFrom(PLOTLINE), "other", "The Other");
    expect(next).toMatchObject({
      continuesInto: "other",
      continuesIntoTitle: "The Other",
      continuesIntoAt: null,
    });
    expect(continueInto(next, null, "ignored")).toMatchObject({
      continuesInto: null,
      continuesIntoTitle: null,
    });
  });

  it("compares drafts by value", () => {
    expect(sameDraft(draftFrom(PLOTLINE), draftFrom(PLOTLINE))).toBe(true);
    expect(sameDraft(draftFrom(PLOTLINE), { ...draftFrom(PLOTLINE), goals: [] })).toBe(
      false,
    );
  });
});

describe("verdicts", () => {
  it.each<[EventFinding[] | undefined, string | null]>([
    [undefined, null],
    [[], null],
    [[finding("info")], "hint"],
    [[finding("info"), finding("conflict")], "conflict"],
  ])("marks findings %j", (findings, expected) => {
    expect(markerOf({ findings })).toBe(expected);
  });

  it.each<[Partial<EventSummary>, string | null]>([
    [{ is_terminus: true, is_convergence: true }, "terminus"],
    [{ is_convergence: true }, "merge"],
    [{ is_divergence: true }, "split"],
    [{}, null],
  ])("reads the role of %j", (flags, expected) => {
    expect(roleOf(flags)).toBe(expected);
  });

  it("lists the scenes in trouble and counts the problems", () => {
    const events = [
      scene("a", { findings: [finding("conflict")] }),
      scene("b", { findings: [finding("info")] }),
    ];
    expect(problemScenes(events).map((e) => e.id)).toEqual(["a"]);
    expect(conflictCount({ conflicts: 2 })).toBe(2);
    expect(conflictCount(undefined)).toBe(0);
  });

  it.each<[string, PlotlineStatus | undefined, string[]]>([
    ["no status", undefined, []],
    [
      "a sound thread",
      { continuation: { state: "ok" }, ends_at_terminus: { state: "ok" } },
      [],
    ],
    [
      "a broken continuation",
      { continuation: { state: "conflicted", message: "The chain loops." } },
      ["The chain loops."],
    ],
    [
      "a thread that stops early",
      {
        ends_at_terminus: {
          state: "conflicted",
          message: "Stops short.",
          evidence: { terminus: "end", last_event: "a" },
        } as never,
      },
      ["Stops short. It ends at 'A'."],
    ],
    [
      "a book with no ending designated",
      {
        ends_at_terminus: {
          state: "conflicted",
          message: "No ending.",
          evidence: {},
        } as never,
      },
      [],
    ],
  ])("notes for %s", (_, status, expected) => {
    expect(verdictNotes(status, [scene("a")])).toEqual(expected);
  });

  it("counts the other threads met on the way, not at the ending", () => {
    const events = [
      scene("a", { shared_with: ["x", "y"] }),
      scene("b", { shared_with: ["y"] }),
      scene("end", { is_terminus: true, shared_with: ["x", "y", "z"] }),
    ];
    expect(meetCount(events)).toBe(2);
  });

  it.each<[Partial<EventSummary>, string | null]>([
    [{ is_terminus: true, is_convergence: true }, null],
    [{ is_convergence: true }, "Threads join here"],
    [{ is_divergence: true }, "A thread departs here"],
    [{ shared_with: ["x"] }, "Shared with 1 other thread"],
    [{ shared_with: ["x", "y"] }, "Shared with 2 other threads"],
    [{}, null],
  ])("hints %j", (flags, expected) => {
    expect(meetHint(scene("s", flags))).toBe(expected);
  });
});

function preview(
  conflicts: number,
  troubled: string[],
  extra: Partial<PlotlineStatus> = {},
): PlotlinePreview {
  return {
    kind: "plotline-preview",
    id: "road",
    events: [],
    goals: [],
    effective_events: ["a", "b", "c"].map((id) =>
      scene(id, troubled.includes(id) ? { findings: [finding("conflict")] } : {}),
    ),
    status: { conflicts, ...extra },
  };
}

describe("compare", () => {
  it("summarizes an order from its preview", () => {
    expect(
      summarize(preview(2, ["a", "c"], { ends_at_terminus: { state: "conflicted" } })),
    ).toEqual({
      problems: 2,
      troubled: ["a", "c"],
      reachesEnding: false,
      continuationHolds: true,
    });
  });

  const s = (
    problems: number,
    reachesEnding = true,
    continuationHolds = true,
  ): OrderSummary => ({
    problems,
    troubled: [],
    reachesEnding,
    continuationHolds,
  });

  it.each<[string, OrderSummary, OrderSummary, string]>([
    ["fewer problems wins", s(2), s(0), "B"],
    ["then reaching the ending", s(1, true), s(1, false), "A"],
    ["then an unbroken continuation", s(0, true, false), s(0, true, true), "B"],
    ["otherwise even", s(1), s(1), "even"],
  ])("%s", (_, a, b, expected) => {
    expect(better(a, b)).toBe(expected);
  });

  it.each<[number, string]>([
    [0, "No problems"],
    [1, "1 problem"],
    [3, "3 problems"],
  ])("headlines %i", (problems, expected) => {
    expect(headline(s(problems))).toBe(expected);
  });

  it("marks the scenes that sit somewhere else in the alternative", () => {
    expect([...movedPositions(["a", "b", "c"], ["a", "c", "b"])].sort()).toEqual([
      "b",
      "c",
    ]);
    expect(movedPositions(["a", "b"], ["a", "b"]).size).toBe(0);
  });
});

describe("focus", () => {
  it.each<[boolean, number, string]>([
    [false, 3, "Hide problems"],
    [true, 1, "Show 1 problem"],
    [true, 2, "Show 2 problems"],
    [true, 0, "Show notes"],
  ])("hidden %s with %i problems reads %j", (hidden, conflicts, expected) => {
    expect(focusLabel(hidden, conflicts)).toBe(expected);
  });

  it.each<[string | null, boolean]>([
    ["1", true],
    ["0", false],
    [null, false],
  ])("reads the stored %j", (stored, expected) => {
    expect(isHidden(stored)).toBe(expected);
  });
});

describe("sections", () => {
  it("runs scenes under each heading into one block", () => {
    const blocks = sections<string>([
      { type: "header", level: 0, label: "Year 1" },
      { type: "event", event: "a", label: "Day 1", depth: 1 },
      { type: "event", event: "b", label: "Day 2", depth: 1 },
      { type: "header", level: 0, label: "Year 2" },
      { type: "event", event: "c", label: "Day 1", depth: 1 },
    ]);
    expect(
      blocks.map((b) =>
        b.kind === "header" ? b.label : b.rows.map((r) => r.event).join(""),
      ),
    ).toEqual(["Year 1", "ab", "Year 2", "c"]);
  });

  it("starts with a block of rows when there are no headings", () => {
    expect(sections<string>([{ type: "event", event: "a", label: "1", depth: 0 }])).toEqual(
      [{ kind: "rows", depth: 0, rows: [{ event: "a", label: "1" }] }],
    );
  });
});
