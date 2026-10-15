import { layoutGoals, type GoalLayout, type LayoutGoal } from "./layout";

const goal = (id: string, depth = 0, depends_on: string[] = []): LayoutGoal => ({
  id,
  title: id,
  depth,
  depends_on,
});

const byId = (out: GoalLayout) => new Map(out.nodes.map((n) => [n.id, n]));
const node = (out: GoalLayout, id: string) => {
  const found = byId(out).get(id);
  if (!found) throw new Error(`no node ${id}`);
  return found;
};

/** The coordinate pairs in a path (`x y`) or a polygon (`x,y`). */
const points = (geometry: string): [number, number][] =>
  [...geometry.matchAll(/(-?[\d.]+)[ ,](-?[\d.]+)/g)].map((m) => [
    Number(m[1]),
    Number(m[2]),
  ]);

type Point = [number, number];

/** An arrowhead's tip and two base corners. */
const corners = (arrow: string): [Point, Point, Point] => {
  const [tip, left, right] = points(arrow);
  if (!tip || !left || !right) throw new Error(`not a triangle: ${arrow}`);
  return [tip, left, right];
};

const edge = (out: GoalLayout, from: string, to: string) => {
  const found = out.edges.find((e) => e.from === from && e.to === to);
  if (!found) throw new Error(`no edge ${from}->${to}`);
  return found;
};

const chain = [goal("claim"), goal("crown", 1, ["claim"])];
const skipping = [
  goal("root"),
  goal("middle", 1, ["root"]),
  goal("far", 2, ["root", "middle"]),
];

describe("rows", () => {
  it("draws a goal below everything it rests on", () => {
    const out = layoutGoals(chain);
    expect(node(out, "claim").y).toBeLessThan(node(out, "crown").y);
    expect([node(out, "claim").depth, node(out, "crown").depth]).toEqual([0, 1]);
  });

  it("puts goals at the same depth on one row", () => {
    const out = layoutGoals([
      goal("a"),
      goal("b"),
      goal("c"),
      goal("all", 1, ["a", "b", "c"]),
    ]);
    expect(new Set(["a", "b", "c"].map((id) => node(out, id).y)).size).toBe(1);
    expect(out.rows).toBe(2);
  });

  it("orders a row to sit under what it rests on, not by name", () => {
    const out = layoutGoals([
      goal("left"),
      goal("right"),
      goal("zeta", 1, ["left"]),
      goal("alpha", 1, ["right"]),
    ]);
    expect(node(out, "left").x).toBeLessThan(node(out, "right").x);
    expect(node(out, "zeta").x).toBeLessThan(node(out, "alpha").x);
    expect(node(out, "zeta").x - node(out, "left").x).toBe(
      node(out, "alpha").x - node(out, "right").x,
    );
  });

  it("lays out the same book the same way whatever order it arrives in", () => {
    const goals = [goal("b"), goal("a"), goal("c", 1, ["a", "b"])];
    expect(layoutGoals([...goals].reverse()).nodes).toEqual(layoutGoals(goals).nodes);
  });

  it("centres rows against the widest one, so one root over three reads as a fan", () => {
    const out = layoutGoals([
      goal("root"),
      ...[0, 1, 2].map((i) => goal(`leaf${i}`, 1, ["root"])),
    ]);
    const leaves = [0, 1, 2].map((i) => node(out, `leaf${i}`));
    const span = [
      Math.min(...leaves.map((n) => n.x)),
      Math.max(...leaves.map((n) => n.x + n.width)),
    ];
    const root = node(out, "root");
    expect(root.x + root.width / 2).toBeCloseTo(((span[0] ?? 0) + (span[1] ?? 0)) / 2);
  });
});

describe("the band of loose goals", () => {
  const graph = [goal("a"), goal("b"), goal("c"), goal("all", 1, ["a", "b", "c"])];

  it("does not widen the graph", () => {
    const joined = layoutGoals(graph);
    const withLoose = layoutGoals([
      ...graph,
      ...[0, 1, 2, 3, 4].map((i) => goal(`loose${i}`)),
    ]);
    expect(withLoose.width).toBe(joined.width);
    expect(withLoose.height).toBeGreaterThan(joined.height);
  });

  it("sits above the graph", () => {
    const out = layoutGoals([...chain, goal("loose")]);
    expect(node(out, "loose").y).toBeLessThan(node(out, "claim").y);
    expect(node(out, "loose").island).toBe(true);
    expect(node(out, "claim").island).toBe(false);
    expect(out.band).toBe(1);
  });

  it("wraps into the width the graph already takes", () => {
    const out = layoutGoals([
      goal("a"),
      goal("b"),
      goal("c", 1, ["a", "b"]),
      ...[0, 1, 2, 3].map((i) => goal(`loose${i}`)),
    ]);
    const lines = new Map<number, string[]>();
    for (const n of out.nodes.filter((n) => n.island))
      lines.set(n.y, [...(lines.get(n.y) ?? []), n.id]);
    expect([...lines.values()].map((ids) => ids.length)).toEqual([2, 2]);
    expect(out.band).toBe(2);
  });

  it.each<[number, number, number]>([
    [9, 3, 3],
    [4, 2, 2],
    [1, 1, 1],
  ])(
    "goes roughly square when %i goals are all loose (%i rows, band %i)",
    (count, rows, band) => {
      const out = layoutGoals(Array.from({ length: count }, (_, i) => goal(`g${i}`)));
      expect([out.rows, out.band]).toEqual([rows, band]);
    },
  );

  it("keeps a loose goal at depth 0 whichever line it wrapped onto", () => {
    const out = layoutGoals([0, 1, 2, 3].map((i) => goal(`g${i}`)));
    expect(new Set(out.nodes.map((n) => n.depth))).toEqual(new Set([0]));
  });

  it("counts a goal whose only prerequisite is gone as loose", () => {
    const out = layoutGoals([...chain, goal("orphan", 0, ["ghost"])]);
    expect(node(out, "orphan").island).toBe(true);
    expect(node(out, "orphan").y).toBeLessThan(node(out, "claim").y);
  });

  it("sets the band apart from the graph", () => {
    const out = layoutGoals([...chain, goal("loose")]);
    const bandToGraph = node(out, "claim").y - node(out, "loose").y;
    const layerToLayer = node(out, "crown").y - node(out, "claim").y;
    expect(bandToGraph).toBeGreaterThan(layerToLayer);
  });
});

describe("edges", () => {
  it("leaves the bottom of one box and lands its arrow on the top of the other", () => {
    const out = layoutGoals(chain);
    const claim = node(out, "claim");
    const crown = node(out, "crown");
    const e = edge(out, "claim", "crown");
    expect(points(e.path)[0]).toEqual([claim.x + claim.width / 2, claim.y + claim.height]);
    expect(points(e.arrow)[0]).toEqual([crown.x + crown.width / 2, crown.y]);
  });

  it("stops the line short, so it cannot show through the head", () => {
    const out = layoutGoals(chain);
    const e = edge(out, "claim", "crown");
    const end = points(e.path).at(-1) ?? [0, 0];
    const tip = points(e.arrow)[0] ?? [0, 0];
    expect(tip[1] - end[1]).toBeCloseTo(10);
    expect(tip[1]).toBe(node(out, "crown").y);
  });

  it("draws the head square to a straight-down line", () => {
    const [tip, left, right] = corners(edge(layoutGoals(chain), "claim", "crown").arrow);
    expect(left[1]).toBe(tip[1] - 10);
    expect(right[1]).toBe(tip[1] - 10);
    expect(left[0]).toBeCloseTo(tip[0] - 3.5);
    expect(right[0]).toBeCloseTo(tip[0] + 3.5);
  });

  it("turns the head with a bowed edge's tangent", () => {
    const out = layoutGoals(skipping);
    const [tip, left, right] = corners(edge(out, "root", "far").arrow);
    expect(left[1]).not.toBe(right[1]);
    const straight = corners(edge(out, "middle", "far").arrow);
    expect(straight[1][1]).toBe(straight[2][1]);
    expect(tip).toEqual(straight[0]);
  });

  it.each<[number, number]>([
    [1, 10],
    [2, 20],
  ])("scales the head with the text (scale %i)", (scale, length) => {
    const [tip, left] = corners(layoutGoals(chain, { scale }).edges[0]?.arrow ?? "");
    expect(tip[1] - left[1]).toBeCloseTo(length);
  });

  it("bows an edge that skips a row clear of the box in between", () => {
    const out = layoutGoals(skipping);
    const long = points(edge(out, "root", "far").path);
    const short = points(edge(out, "middle", "far").path);
    const start = long[0]?.[0] ?? 0;
    expect(long.slice(1, 3).every(([x]) => Math.abs(x - start) > 20)).toBe(true);
    expect(short.slice(1, 3).every(([x]) => x === short[0]?.[0])).toBe(true);
  });

  it("leaves a dependency that is not in the book undrawn", () => {
    expect(layoutGoals([goal("crown", 0, ["ghost"])]).edges).toEqual([]);
  });
});

describe("bad data", () => {
  it("still draws every goal of a loop", () => {
    const out = layoutGoals([goal("a", 0, ["b"]), goal("b", 0, ["a"])]);
    expect(new Set(out.nodes.map((n) => n.id))).toEqual(new Set(["a", "b"]));
    expect(out.edges).toHaveLength(2);
  });

  it("lays out an empty book without falling over", () => {
    const out = layoutGoals([]);
    expect([out.nodes, out.edges]).toEqual([[], []]);
    expect(out.width).toBeGreaterThan(0);
    expect(out.height).toBeGreaterThan(0);
  });

  it("draws a goal whose depth is out of range on a last row", () => {
    const out = layoutGoals([
      goal("a"),
      goal("b", 1, ["a"]),
      { id: "odd", depth: Number.NaN, depends_on: ["a"] },
    ]);
    expect(byId(out).has("odd")).toBe(true);
  });
});
