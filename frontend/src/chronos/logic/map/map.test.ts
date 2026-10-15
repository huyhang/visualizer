// The story map's pure rules, ported from the classic page's
// tests/chronos/test_graph_js.py so the React map is held to the same cases.

import { collapseRuns } from "./collapse";
import { edgeShape, strokeClass } from "./edges";
import { applyPeriodGrouping } from "./grouping";
import { geometry, layoutGraph } from "./layout";
import { orderLanes } from "./lanes";
import { connectedIds, connectedTo, restrictTo } from "./subgraph";
import { PATHS, atOnce, cost, drift, fourThreads, graphOf } from "./testGraphs";

const ALL = Object.keys(PATHS);

describe("which threads are in", () => {
  it.each<[string[], string[]]>([
    [
      ["alpha", "beta"],
      ["T", "a1", "a2", "a3", "a4", "b1", "b2", "b3", "j1", "j2"],
    ],
    [["gamma"], ["T", "c1", "j2"]],
    [[], []],
  ])("restricting to %j keeps exactly their scenes", (ids, nodes) => {
    const slice = restrictTo(fourThreads(), ids);
    expect(slice.plotlines.map((p) => p.id)).toEqual(ids);
    expect(slice.nodes.map((n) => n.id).sort()).toEqual(nodes);
  });

  it("drops edges that would dangle and untags hidden threads", () => {
    const slice = restrictTo(fourThreads(), ["alpha", "beta"]);
    const ids = new Set(slice.nodes.map((n) => n.id));
    expect(slice.edges.filter((e) => !ids.has(e.from) || !ids.has(e.to))).toEqual([]);
    expect([...new Set(slice.edges.flatMap((e) => e.plotlines))].sort()).toEqual([
      "alpha",
      "beta",
    ]);
    expect(slice.terminus).toBe("T");
  });

  it.each<[string, string[]]>([
    ["alpha", ["alpha", "beta"]],
    ["beta", ["alpha", "beta", "gamma"]],
    ["delta", ["delta"]],
    ["nobody", []],
  ])("the threads meeting %s, not counting the ending", (focus, expected) => {
    expect([...connectedIds(fourThreads(), focus)].sort()).toEqual(expected);
  });

  it("lets any shared scene connect when the book has no ending yet", () => {
    const g = { ...fourThreads(), terminus: null };
    expect([...connectedIds(g, "delta")].sort()).toEqual(ALL.slice().sort());
  });

  it("records the focus on the connected slice", () => {
    expect(connectedTo(fourThreads(), "alpha").focus).toBe("alpha");
  });
});

describe("how much of them is drawn", () => {
  const dense = (ids: string[], expanded: string[] = []) =>
    collapseRuns(restrictTo(fourThreads(), ids), { expanded: new Set(expanded) });

  it("folds a solitary run into one band, leaving every junction", () => {
    const d = dense(ALL);
    expect(d.bands).toEqual([
      { id: "~run:alpha:a1", lane: "alpha", events: ["a1", "a2", "a3", "a4"] },
      { id: "~run:beta:b1", lane: "beta", events: ["b1", "b2", "b3"] },
    ]);
    const ids = d.nodes.map((n) => n.id);
    for (const gone of ["a1", "a2", "a3", "a4", "b1", "b2", "b3"])
      expect(ids).not.toContain(gone);
    for (const junction of ["j1", "j2", "T"]) expect(ids).toContain(junction);
    expect(d.plotlines.find((p) => p.id === "alpha")?.effective_events).toEqual([
      "~run:alpha:a1",
      "j1",
      "T",
    ]);
  });

  it("leaves a run shorter than the minimum alone", () => {
    const d = dense(["gamma", "delta"]);
    expect(d.bands).toEqual([]);
    expect(d.nodes.map((n) => n.id).sort()).toEqual(["T", "c1", "d1", "d2", "j2"]);
  });

  it("shows an unfolded band's scenes again but still finds it", () => {
    const d = dense(["alpha", "beta"], ["~run:alpha:a1"]);
    const ids = d.nodes.map((n) => n.id);
    expect(ids).toEqual(expect.arrayContaining(["a1", "a2", "a3", "a4", "~run:beta:b1"]));
    expect(ids).not.toContain("~run:alpha:a1");
    expect(d.bands.map((b) => b.id)).toEqual(["~run:alpha:a1", "~run:beta:b1"]);
  });

  it("rewires the edges around a band", () => {
    const edges = dense(["alpha", "beta"]).edges.map((e) => `${e.from}->${e.to}`);
    expect(edges).toEqual(
      expect.arrayContaining(["~run:alpha:a1->j1", "j1->~run:beta:b1"]),
    );
    expect(edges.filter((e) => e.startsWith("a2") || e.endsWith("a3"))).toEqual([]);
  });

  it.each<[string[], string[]]>([
    [
      ["alpha", "beta", "gamma"],
      ["b1", "b2", "b3"],
    ],
    [
      ["alpha", "beta"],
      ["b1", "b2", "b3", "j2"],
    ],
  ])("a junction only a hidden thread made stops being one (%j)", (ids, run) => {
    expect(dense(ids).bands.find((b) => b.lane === "beta")?.events).toEqual(run);
  });
});

describe("where the lanes go", () => {
  it("puts the threads that meet side by side, tidier than the book", () => {
    const got = orderLanes(fourThreads().plotlines, { terminus: "T" }).map((p) => p.id);
    expect(cost(got, PATHS)).toBeLessThan(cost(ALL, PATHS));
    expect(Math.abs(got.indexOf("alpha") - got.indexOf("beta"))).toBe(1);
    expect(Math.abs(got.indexOf("gamma") - got.indexOf("beta"))).toBe(1);
  });

  it("is deterministic and never worse than the order given", () => {
    const g = fourThreads();
    const once = orderLanes(g.plotlines, { terminus: "T" }).map((p) => p.id);
    expect(orderLanes(g.plotlines, { terminus: "T" }).map((p) => p.id)).toEqual(once);
    const flipped = orderLanes([...g.plotlines].reverse(), { terminus: "T" }).map(
      (p) => p.id,
    );
    expect(cost(flipped, PATHS)).toBeLessThanOrEqual(cost([...ALL].reverse(), PATHS));
  });

  it("keeps a thread's colour when the selection changes", () => {
    const colorOf = (id: string) => `c${ALL.indexOf(id)}`;
    const of = (ids: string[]) =>
      Object.fromEntries(
        layoutGraph(restrictTo(fourThreads(), ids), { colorOf }).lanes.map((l) => [
          l.id,
          l.color,
        ]),
      );
    const pair = of(["alpha", "beta"]);
    const all = of(ALL);
    expect(pair.alpha).toBe(all.alpha);
    expect(pair.beta).toBe(all.beta);
  });

  it("gives a thread that owns no column no width", () => {
    // trunk's every scene sits on an earlier lane, so it is never drawn in a column of its own.
    const g = graphOf({ branch: ["x", "end"], trunk: ["end"] }, { x: 0, end: 10 }, "end");
    const layout = layoutGraph(restrictTo(g, ["branch", "trunk"]));
    expect(layout.width).toBe(geometry.PAD_X + geometry.COL_W);
    expect(layout.lanes.find((l) => l.id === "trunk")?.column).toBeNull();
  });

  it("asks for width rather than squeezing the titles", () => {
    const layout = layoutGraph(restrictTo(fourThreads(), ALL));
    expect(layout.minWidth).toBeGreaterThanOrEqual(layout.width + geometry.TEXT_MIN);
  });
});

describe("rows and heights", () => {
  const slice = () => restrictTo(fourThreads(), ["alpha"]);
  const yOf = (nodes: { id: string; y: number }[]) =>
    Object.fromEntries(nodes.map((n) => [n.id, n.y]));

  it("pushes the rows below an opened row down, edges and all", () => {
    const flat = layoutGraph(slice());
    const grown = layoutGraph(slice(), {
      heightOf: (n) => (n.id === "a2" ? geometry.ROW_H + 200 : geometry.ROW_H),
    });
    const [f, g] = [yOf(flat.nodes), yOf(grown.nodes)];
    expect(g.a1).toBe(f.a1);
    expect(g.a2).toBe((f.a2 ?? 0) + 100);
    for (const below of ["a3", "a4", "j1", "T"])
      expect(g[below]).toBe((f[below] ?? 0) + 200);
    const edge = (l: typeof flat) => l.edges.find((e) => e.from === "a4" && e.to === "j1");
    expect(edge(grown)?.y1).toBe((edge(flat)?.y1 ?? 0) + 200);
    expect(grown.height).toBe(flat.height + 200);
  });

  it("honours row heights under the period headings too", () => {
    const tall = (n: { id: string }) =>
      n.id === "a2" ? geometry.ROW_H + 120 : geometry.ROW_H;
    const flat = applyPeriodGrouping(layoutGraph(slice()));
    const grown = applyPeriodGrouping(layoutGraph(slice(), { heightOf: tall }), {
      heightOf: tall,
    });
    expect(flat.headers.map((h) => h.label)).toEqual(["Year 1"]);
    expect(flat.nodes.every((n) => typeof n.when === "string")).toBe(true);
    const [f, g] = [yOf(flat.nodes), yOf(grown.nodes)];
    expect(g.a1).toBe(f.a1);
    for (const below of ["a3", "a4", "j1", "T"])
      expect(g[below]).toBe((f[below] ?? 0) + 120);
  });

  it("lets a band ride as an ordinary row, where its scenes were", () => {
    const model = applyPeriodGrouping(
      layoutGraph(collapseRuns(restrictTo(fourThreads(), ALL))),
    );
    const rows = [...model.nodes].sort((a, b) => a.y - b.y).map((n) => n.id);
    expect(rows.indexOf("~run:alpha:a1")).toBeLessThan(rows.indexOf("j1"));
    expect(rows.indexOf("j1")).toBeLessThan(rows.indexOf("~run:beta:b1"));
    expect(rows.indexOf("~run:alpha:a1")).toBeLessThan(rows.indexOf("d1"));
    expect(rows.at(-1)).toBe("T");
    const band = model.nodes.find((n) => n.id === "~run:alpha:a1");
    expect(band).toMatchObject({ isBand: true, title: "4 scenes on Alpha" });
    expect(band?.when).toBeTruthy();
  });

  it("puts every drawn node on exactly one row, in the drawing order", () => {
    const model = applyPeriodGrouping(
      layoutGraph(collapseRuns(restrictTo(fourThreads(), ["alpha", "beta"]))),
    );
    const onRows = model.rows.flatMap((r) => r.nodes.map((n) => n.id)).sort();
    expect(onRows).toEqual(model.nodes.map((n) => n.id).sort());
    expect(model.sequence.filter((e) => e.kind === "row")).toHaveLength(model.rows.length);
    expect(model.sequence[0]?.kind).toBe("header");
  });
});

describe("rows in time order", () => {
  it("does not drag an undated scene's thread to the bottom", () => {
    const layout = layoutGraph(restrictTo(drift(), ["drifting", "long"]));
    const rows = [...layout.nodes].sort((a, b) => a.row - b.row).map((n) => n.id);
    expect(rows.indexOf("early")).toBeLessThan(rows.indexOf("next-year"));
    expect(rows.indexOf("ending")).toBeLessThan(rows.indexOf("next-year"));
    expect(rows.indexOf("opens")).toBeLessThan(rows.indexOf("undated"));
    expect(rows.indexOf("undated")).toBeLessThan(rows.indexOf("early"));
  });

  it("never lets the calendar rail double back, folded or not", () => {
    const slice = restrictTo(drift(), ["drifting", "long"]);
    const years = (d: ReturnType<typeof collapseRuns>) =>
      applyPeriodGrouping(layoutGraph(d))
        .headers.filter((h) => h.level === 0)
        .map((h) => h.label);
    const folded = collapseRuns(slice, { minRun: 2 });
    const opened = collapseRuns(slice, {
      minRun: 2,
      expanded: new Set(folded.bands.map((b) => b.id)),
    });
    expect(years(collapseRuns(slice))).toEqual(["Year 1", "Year 2"]);
    expect(years(folded)).toEqual([...years(folded)].sort());
    expect(years(opened)).toEqual([...years(opened)].sort());
  });
});

describe("scenes at one moment", () => {
  const model = (shut: string[] = []) =>
    applyPeriodGrouping(layoutGraph(restrictTo(atOnce(), ["knight", "spy"])), {
      collapsedMoments: new Set(shut),
    });

  it("share one slot and one y, still in time order", () => {
    const m = model();
    const groups = m.rows
      .filter((r) => r.isGroup)
      .map((r) => r.nodes.map((n) => n.id).sort());
    expect(groups).toEqual([
      ["open-a", "open-b"],
      ["betrayal", "duel"],
    ]);
    const y = Object.fromEntries(m.nodes.map((n) => [n.id, n.y]));
    expect(y.duel).toBe(y.betrayal);
    expect(y["open-a"]).toBeLessThan(y.duel ?? 0);
    expect(y.duel).toBeLessThan(y.aftermath ?? 0);
    expect({ rows: m.rows.length, nodes: m.nodes.length }).toEqual({ rows: 4, nodes: 6 });
  });

  it("hide behind their count when closed, keeping the same moments", () => {
    const shut = model(["~at:100:betrayal"]);
    const at = (id: string) => shut.rows.find((r) => r.nodes.some((n) => n.id === id));
    expect(shut.rows).toHaveLength(4);
    expect(at("duel")).toMatchObject({ id: "~at:100:betrayal", collapsed: true, count: 2 });
    expect(at("open-a")?.collapsed).toBe(false);
  });

  it.each<[string, () => ReturnType<typeof model>]>([
    [
      "scenes at different ticks",
      () => applyPeriodGrouping(layoutGraph(restrictTo(fourThreads(), ALL))),
    ],
    [
      "undated scenes",
      () => applyPeriodGrouping(layoutGraph(restrictTo(drift(), ["drifting", "long"]))),
    ],
  ])("never groups %s", (_, build) => {
    expect(build().rows.filter((r) => r.isGroup)).toEqual([]);
  });
});

describe("edge shapes", () => {
  it.each<[string, [number, number, number, number], string]>([
    ["a thread staying in its lane is straight", [22, 100, 22, 158], "M 22 100 L 22 158"],
    [
      "a joining thread holds its column until the turn",
      [56, 173, 22, 289],
      "M 56 173 V 254 Q 56 289, 22 289",
    ],
    [
      "a departing thread turns out at once",
      [22, 100, 56, 300],
      "M 22 100 Q 56 100, 56 135 V 300",
    ],
  ])("%s", (_, [x1, y1, x2, y2], d) => {
    expect(edgeShape({ x1, y1, x2, y2 })).toBe(d);
  });

  it("turns earlier the further a thread reaches", () => {
    const turnAt = (d: string) => Number(d.split("V")[1]?.split("Q")[0]);
    const near = turnAt(edgeShape({ x1: 56, y1: 100, x2: 22, y2: 300 }));
    const far = turnAt(edgeShape({ x1: 158, y1: 100, x2: 22, y2: 300 }));
    expect(far).toBeLessThan(near);
  });

  it("never lets two threads joining one node share a column", () => {
    const joining = edgeShape({ x1: 56, y1: 173, x2: 22, y2: 289 });
    expect(Number(joining.split("V")[1]?.split("Q")[0])).toBeGreaterThan(231);
  });

  it.each<[string, string]>([
    ["", ""],
    ["7 4", "is-dashed"],
    ["2 4", "is-dotted"],
  ])("marks the stroke %j as %j", (dash, cls) => {
    expect(strokeClass(dash)).toBe(cls);
  });
});

describe("threads past the palette", () => {
  it("stay distinct by colour and stroke together", () => {
    const n = 26;
    const paths = Object.fromEntries(
      Array.from({ length: n }, (_, i) => [`p${i}`, [`s${i}`, "end"]]),
    );
    const ticks: Record<string, number> = Object.fromEntries(
      Array.from({ length: n }, (_, i) => [`s${i}`, i * 10]),
    );
    const g = graphOf(paths, { ...ticks, end: 9999 }, "end");
    const lanes = layoutGraph(restrictTo(g, Object.keys(paths))).lanes;
    expect(new Set(lanes.map((l) => l.color)).size).toBe(12);
    expect([...new Set(lanes.map((l) => l.dash))].sort()).toEqual(["", "2 4", "7 4"]);
    expect(new Set(lanes.map((l) => `${l.color}|${l.dash}`)).size).toBe(26);
  });
});
