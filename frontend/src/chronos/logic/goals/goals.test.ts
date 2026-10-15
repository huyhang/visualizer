import { ChronosApiError } from "../../api/errors";
import type { Goal } from "../../api/types";
import { GOALS } from "../../test/fixtures";
import {
  blockersFromRefusal,
  blockersOf,
  draftFor,
  goalBody,
  noBlockers,
  offerable,
  saveFailure,
  withId,
  withTitle,
} from "./draft";
import {
  boxSubtitle,
  boxWhen,
  edgeOnChain,
  inFocus,
  inReadingOrder,
  lineage,
  matchesFilter,
  summaryLine,
  whenLine,
} from "./goals";

const g = (id: string, depends_on: string[] = [], extra: Partial<Goal> = {}): Goal => ({
  kind: "goal",
  id,
  book: "b",
  title: id,
  depends_on,
  dependencies: [],
  required_by: [],
  plotlines: [],
  depth: 0,
  rev: 1,
  status: { state: "open", findings: [] },
  ...extra,
});

// a <- b <- c, and d rests on b too; e stands alone.
const BOOK = [g("a"), g("b", ["a"]), g("c", ["b"]), g("d", ["b"]), g("e")];
const scene = (title: string, when?: string) => ({ id: "s", title, when });

describe("inReadingOrder", () => {
  it("puts prerequisites first, then names", () => {
    const goals = [
      g("zed", [], { depth: 0, title: "Zed" }),
      g("top", [], { depth: 1, title: "Top" }),
      g("alp", [], { depth: 0, title: "Alp" }),
    ];
    expect(inReadingOrder(goals).map((x) => x.id)).toEqual(["alp", "zed", "top"]);
  });
});

describe("matchesFilter", () => {
  it.each<[string, boolean]>([
    ["", true],
    ["ember", true],
    ["seal deliver", true],
    ["harbor", true],
    ["dragon", false],
  ])("%j", (query, expected) => {
    expect(
      matchesFilter(
        { id: "seal", title: "Deliver the Ember Seal", description: "Reaches the harbor." },
        query,
      ),
    ).toBe(expected);
  });
});

describe("lineage", () => {
  it.each<[string, string[], string[]]>([
    ["a", [], ["b", "c", "d"]],
    ["b", ["a"], ["c", "d"]],
    ["c", ["a", "b"], []],
    ["e", [], []],
  ])("of %s", (id, ancestors, descendants) => {
    const chain = lineage(BOOK, id);
    expect([...chain.ancestors].sort()).toEqual(ancestors);
    expect([...chain.descendants].sort()).toEqual(descendants);
  });

  it("survives a loop", () => {
    const chain = lineage([g("x", ["y"]), g("y", ["x"])], "x");
    expect([...chain.ancestors]).toEqual(["y"]);
    expect([...chain.descendants]).toEqual(["y"]);
  });

  it.each<[string, string, boolean]>([
    ["a", "b", true],
    ["b", "c", true],
    ["b", "d", true],
    ["x", "y", false],
  ])("lights the edge %s→%s on c's chain or b's", (from, to, expected) => {
    const lit =
      edgeOnChain({ from, to }, "b", lineage(BOOK, "b")) ||
      edgeOnChain({ from, to }, "c", lineage(BOOK, "c"));
    expect(lit).toBe(expected);
  });

  it("does not light a sibling's edge", () => {
    expect(edgeOnChain({ from: "b", to: "d" }, "c", lineage(BOOK, "c"))).toBe(false);
  });

  it.each<[string, string | null, boolean]>([
    ["e", null, true],
    ["b", "b", true],
    ["a", "c", true],
    ["d", "c", false],
    ["e", "c", false],
  ])("keeps %s in focus when %s is selected", (id, selected, expected) => {
    expect(inFocus(id, selected, selected ? lineage(BOOK, selected) : null)).toBe(expected);
  });
});

describe("box and card lines", () => {
  it.each<[Partial<Goal>, string]>([
    [
      { status: { state: "conflicted", findings: [] }, achieved_scene: scene("X") },
      "needs attention",
    ],
    [{ achieved_scene: scene("The Coronation") }, "✓ The Coronation"],
    [{}, "no scene yet"],
  ])("subtitles %j", (extra, expected) => {
    expect(boxSubtitle(g("x", [], extra))).toBe(expected);
  });

  it.each<[string | undefined, string]>([
    ["Day 3 → Day 4", "Day 3"],
    ["Day 3", "Day 3"],
    [undefined, ""],
  ])("dates a box from %j", (when, expected) => {
    expect(boxWhen({ achieved_scene: scene("X", when) })).toBe(expected);
  });

  it.each<[Goal["achieved_scene"], string, string | null]>([
    [scene("The Coronation", "Day 9"), "The Coronation", "The Coronation · Day 9"],
    [scene("The Coronation"), "The Coronation", "The Coronation"],
    [null, "no scene yet", null],
  ])("reads where it lands (%j)", (achieved, summary, when) => {
    expect(summaryLine({ achieved_scene: achieved })).toBe(summary);
    expect(whenLine({ achieved_scene: achieved })).toBe(when);
  });
});

describe("the draft", () => {
  it("lets a new goal's id follow its title until the writer takes it over", () => {
    let draft = withTitle(draftFor(null), "Deliver the Seal");
    expect(draft.id).toBe("deliver-the-seal");
    draft = withTitle(withId(draft, " seal "), "Deliver the Ember Seal");
    expect(draft.id).toBe("seal");
  });

  it("never moves an existing goal's id", () => {
    const seal = GOALS[0] as Goal;
    expect(withTitle(draftFor(seal), "Something else").id).toBe("seal");
  });

  it.each<[string, Partial<ReturnType<typeof draftFor>>, ReturnType<typeof goalBody>]>([
    [
      "clears a blank title and an unset scene by saying so",
      { title: "  ", description: "d", dependsOn: ["a"] },
      { title: null, description: "d", depends_on: ["a"], achieved_at: null },
    ],
    [
      "sends what was chosen",
      { title: " Crown ", achievedAt: "coronation" },
      { title: "Crown", description: "", depends_on: [], achieved_at: "coronation" },
    ],
  ])("%s", (_, changes, body) => {
    expect(goalBody({ ...draftFor(null), ...changes })).toEqual(body);
  });

  it.each<[string, string[], string, string[]]>([
    ["a new goal may rest on anything", [], "", ["a", "b", "c", "d", "e"]],
    ["never on itself, or on what already rests on it", [], "b", ["a", "e"]],
    ["nor twice on the same one", ["a"], "e", ["b", "c", "d"]],
  ])("offers prerequisites: %s", (_, dependsOn, id, expected) => {
    expect(offerable(BOOK, { id, dependsOn }).map((x) => x.id)).toEqual(expected);
  });

  it("narrows the offer by what was typed", () => {
    expect(offerable(BOOK, { id: "", dependsOn: [] }, "c").map((x) => x.id)).toEqual(["c"]);
  });
});

describe("saveFailure", () => {
  it.each<[unknown, string]>([
    [
      new ChronosApiError(409, "x", "ALREADY_EXISTS"),
      "A goal with the id “seal” already exists. Choose another.",
    ],
    [
      new ChronosApiError(400, "x", "GOAL_CYCLE", { cycle: ["seal", "crown", "seal"] }),
      "That would make the goals loop: seal → crown → seal.",
    ],
    [new ChronosApiError(400, "x", "GOAL_CYCLE"), "That would make the goals loop."],
    [
      new ChronosApiError(409, "x", "REVISION_CONFLICT"),
      "Someone else changed this goal since you opened it. Close this and open it again to see their version.",
    ],
    [new ChronosApiError(400, "Title too long.", "INVALID_GOAL"), "Title too long."],
    ["nonsense", "Could not save the goal."],
  ])("reads %s", (error, expected) => {
    expect(saveFailure(error, "seal")).toBe(expected);
  });
});

describe("blockers", () => {
  it("names the threads serving a goal and the goals resting on it", () => {
    const seal = GOALS[0] as Goal;
    expect(blockersOf(seal)).toEqual({
      threads: [{ id: "road", title: "The Knight's Road" }],
      goals: [{ id: "crown", title: "See the crown pressed" }],
    });
  });

  it.each<[unknown, ReturnType<typeof blockersFromRefusal>]>([
    [
      new ChronosApiError(409, "x", "GOAL_IN_USE", {
        plotlines: ["road", "gone"],
        goals: ["crown"],
      }),
      {
        threads: [
          { id: "road", title: "Road" },
          { id: "gone", title: "gone" },
        ],
        goals: [{ id: "crown", title: "Crown" }],
      },
    ],
    [new ChronosApiError(409, "x", "REVISION_CONFLICT"), null],
  ])("reads the server's refusal %#", (error, expected) => {
    const titles: Record<string, string> = { road: "Road", crown: "Crown" };
    expect(
      blockersFromRefusal(
        error,
        (id) => titles[id],
        (id) => titles[id],
      ),
    ).toEqual(expected);
  });

  it.each<
    [
      { threads: { id: string; title: string }[]; goals: { id: string; title: string }[] },
      boolean,
    ]
  >([
    [{ threads: [], goals: [] }, true],
    [{ threads: [{ id: "x", title: "x" }], goals: [] }, false],
  ])("knows when nothing is in the way (%j)", (blockers, expected) => {
    expect(noBlockers(blockers)).toBe(expected);
  });
});
