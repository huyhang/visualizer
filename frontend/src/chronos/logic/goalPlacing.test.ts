import type { GoalRef } from "../api/types";
import {
  ELSEWHERE,
  MISSING,
  NO_SCENE,
  anyUnplaced,
  coverageOf,
  eachAlone,
  placeGoals,
  pursuedBy,
  stripFor,
} from "./goalPlacing";

function ref(
  id: string,
  at: string | null = null,
  scene?: string,
  when?: string | null,
): GoalRef {
  return {
    id,
    title: id[0]?.toUpperCase() + id.slice(1),
    missing: false,
    achieved_at: at,
    achieved_scene:
      at === null ? null : { id: at, title: scene ?? at, when: when ?? undefined },
  };
}
const ghost: GoalRef = { id: "ghost", title: "ghost", missing: true };

const marksOf = (refs: GoalRef[], nodes: string[]) =>
  Object.fromEntries(
    [...placeGoals(refs, eachAlone(nodes)).marks].map(([n, rs]) => [
      n,
      rs.map((r) => r.id),
    ]),
  );

describe("placeGoals: marks", () => {
  it.each<[string, GoalRef[], string[], Record<string, string[]>]>([
    [
      "on the scene that delivers it",
      [ref("crown", "s2")],
      ["s1", "s2", "s3"],
      { s2: ["crown"] },
    ],
    [
      "two goals on one scene both ride on it",
      [ref("crown", "s1"), ref("peace", "s1")],
      ["s1"],
      { s1: ["crown", "peace"] },
    ],
    [
      "nothing on a scene no goal names",
      [ref("crown", "s1")],
      ["s1", "s2"],
      { s1: ["crown"] },
    ],
  ])("%s", (_, refs, nodes, expected) => {
    expect(marksOf(refs, nodes)).toEqual(expected);
  });
});

describe("placeGoals: the three ways to be unplaced", () => {
  it.each<[string, GoalRef, string, string]>([
    ["no scene yet", ref("crown"), NO_SCENE, "no scene yet"],
    [
      "delivered off this view",
      ref("crown", "s9", "The Coronation", "Year 3, Moon 4"),
      ELSEWHERE,
      "delivered at The Coronation · Year 3, Moon 4",
    ],
    [
      "delivered at an undated scene",
      ref("crown", "s9", "The Coronation", null),
      ELSEWHERE,
      "delivered at The Coronation",
    ],
    ["a dangling id", ghost, MISSING, "no longer in this book"],
    [
      "a scene that left the book",
      {
        id: "crown",
        title: "Crown",
        missing: false,
        achieved_at: "s9",
        achieved_scene: null,
      },
      ELSEWHERE,
      "delivered by a scene that is no longer in the book",
    ],
  ])("%s", (_, goal, reason, note) => {
    const [missed] = placeGoals([goal], eachAlone(["s1"])).unplaced;
    expect(missed).toMatchObject({ id: goal.id, reason, note });
  });

  it("marks or names every goal: nothing falls off the page", () => {
    const placed = placeGoals(
      [ref("a", "s1"), ref("b", "s2"), ref("c"), ref("d", "far"), ghost],
      eachAlone(["s1", "s2"]),
    );
    const marked = [...placed.marks.values()].flat().map((r) => r.id);
    expect([...marked, ...placed.unplaced.map((g) => g.id)].sort()).toEqual([
      "a",
      "b",
      "c",
      "d",
      "ghost",
    ]);
    expect(anyUnplaced(placed)).toBe(true);
  });
});

describe("folded runs", () => {
  it("marks a goal landing inside a band on the band", () => {
    const coverage = coverageOf([
      { id: "band:1", is_band: true, events: ["s1", "s2"] },
      { id: "s3" },
    ]);
    expect(
      placeGoals([ref("crown", "s2")], coverage)
        .marks.get("band:1")
        ?.map((r) => r.id),
    ).toEqual(["crown"]);
  });
});

describe("the strip", () => {
  it("names only unplaced goals the shown threads pursue", () => {
    const placed = placeGoals([ref("mine"), ref("theirs")], eachAlone([]));
    expect(stripFor(placed, [{ goals: ["mine"] }]).map((g) => g.id)).toEqual(["mine"]);
  });

  it.each<[{ goals?: string[] }[], string[]]>([
    [[], []],
    [
      [{ goals: ["a"] }, { goals: ["a", "b"] }, {}],
      ["a", "b"],
    ],
  ])("collects what %j pursue", (lanes, expected) => {
    expect([...pursuedBy(lanes)].sort()).toEqual(expected);
  });
});
