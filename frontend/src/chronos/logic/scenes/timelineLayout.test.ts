// Ported from tests/chronos/test_scene_timeline_js.py, which still holds the
// classic page's timelinelayout.js to the same rules.

import {
  CARD_HEIGHT,
  densityBins,
  displayPlacements,
  distanceToScene,
  periodBands,
  railGeometry,
  scaleFor,
  scrollForTick,
  seedLabels,
  stepZoom,
  storyOrder,
  tickAtRatio,
  ratioForTick,
  tickAtScroll,
  visibleBreaks,
  visiblePeriods,
  visibleScenes,
  type Placement,
  type RailScene,
} from "./timelineLayout";

const scene = (id: string, start: number, end: number, title?: string): RailScene => ({
  id,
  title: title ?? id,
  start_tick: start,
  end_tick: end,
});

function dated(id: string, start: number, end: number, parts: string[]): RailScene {
  return {
    ...scene(id, start, end),
    scheduled: true,
    start_parts: parts,
    end_parts: parts,
    start_label: parts.join(", "),
    end_label: parts.join(", "),
  };
}

describe("the clock", () => {
  it.each<[number]>([[-20], [-100], [0], [100]])(
    "maps tick %i to a scroll and back, even before tick zero",
    (tick) => {
      const scale = scaleFor(
        { start_tick: -100, end_tick: 100 },
        { viewportHeight: 600, eventCount: 10 },
      );
      expect(tickAtScroll(scale, scrollForTick(scale, tick))).toBe(tick);
      expect(scale.startTick).toBe(-100);
    },
  );

  it.each<[number, number]>([
    [15, 0],
    [5, 5],
    [26, 6],
  ])("measures the distance from a scene at 10–20 to tick %i as %i", (tick, expected) => {
    expect(distanceToScene(scene("voyage", 10, 20), tick)).toBe(expected);
  });

  it("keeps a cursor tick addressable across a zoom", () => {
    const bounds = { start_tick: 0, end_tick: 100 };
    const one = scaleFor(bounds, { viewportHeight: 600, eventCount: 20, zoom: 1 });
    const four = scaleFor(bounds, { viewportHeight: 600, eventCount: 20, zoom: 4 });
    const tick = tickAtScroll(one, scrollForTick(one, 75));
    expect(tickAtScroll(four, scrollForTick(four, tick))).toBe(75);
  });

  it.each<[number, number, number]>([
    [1, 1, 2],
    [1, -1, 0.5],
    [8, 1, 8],
    [0.5, -1, 0.5],
    [3, 1, 2],
  ])("steps zoom %f by %i to %f", (zoom, direction, expected) => {
    expect(stepZoom(zoom, direction)).toBe(expected);
  });

  it("reads the overview's ratio back as the same tick", () => {
    const scale = scaleFor(
      { start_tick: 0, end_tick: 100 },
      { viewportHeight: 600, eventCount: 4 },
    );
    expect(tickAtRatio(scale, ratioForTick(scale, 40))).toBe(40);
  });
});

describe("story order", () => {
  it("ranks every scene once, earliest first", () => {
    const order = storyOrder([scene("late", 90, 95), scene("early", 10, 20)]);
    expect(order.ordered.map((s) => s.id)).toEqual(["early", "late"]);
    expect([...order.rank]).toEqual([
      ["early", 0],
      ["late", 1],
    ]);
  });
});

describe("the cards around the cursor", () => {
  it("does not mount far scenes", () => {
    const events = [scene("near", 50, 55), scene("far", 950, 960)];
    const scale = scaleFor(
      { start_tick: 0, end_tick: 1000 },
      { viewportHeight: 600, eventCount: 2, zoom: 4 },
    );
    expect(
      visibleScenes(storyOrder(events), scale, 50).cards.map((p) => p.scene.id),
    ).toEqual(["near"]);
  });

  it("gives simultaneous scenes one anchor and parallel lanes", () => {
    const events = [
      scene("short", 10, 12, "Zulu"),
      scene("long-z", 10, 30, "Zulu"),
      scene("long-a", 10, 30, "Alpha"),
    ];
    const scale = scaleFor(
      { start_tick: 0, end_tick: 40 },
      { viewportHeight: 600, eventCount: 3 },
    );
    const cards = visibleScenes(storyOrder(events), scale, 10).cards;
    expect(cards.map((c) => c.scene.id)).toEqual(["long-a", "long-z", "short"]);
    expect(new Set(cards.map((c) => c.anchorY)).size).toBe(1);
    expect(cards.slice(0, 2).map((c) => c.side)).toEqual([0, 1]);
  });

  it("never splits a simultaneous moment at the render limit", () => {
    const events = [0, 1, 2, 3, 4].map((i) => scene(`e${i}`, 10, 20));
    const scale = scaleFor(
      { start_tick: 0, end_tick: 40 },
      { viewportHeight: 600, eventCount: 5 },
    );
    expect(
      visibleScenes(storyOrder(events), scale, 10, { maxScenes: 2 }).cards,
    ).toHaveLength(5);
  });

  it("mounts no card where the stage cannot show it", () => {
    const events = Array.from({ length: 60 }, (_, i) => scene(`e${i}`, i * 4, i * 4 + 2));
    const scale = scaleFor(
      { start_tick: 0, end_tick: 240 },
      { viewportHeight: 600, events, eventCount: 60 },
    );
    const order = storyOrder(events);
    let worst = 0;
    let mounted = 0;
    for (let step = 0; step <= 40; step++) {
      const tick = tickAtScroll(scale, (step / 40) * scale.runHeight);
      const { cards } = visibleScenes(order, scale, tick, { viewportHeight: 600 });
      mounted = Math.max(mounted, cards.length);
      worst = Math.max(
        worst,
        cards.filter((c) => c.top >= 600 || c.top + CARD_HEIGHT <= 0).length,
      );
    }
    expect(worst).toBe(0);
    expect(mounted).toBeGreaterThan(0);
  });

  it("stacks earlier scenes above the rule and later ones below", () => {
    const events = Array.from({ length: 12 }, (_, i) => scene(`e${i}`, i * 10, i * 10 + 2));
    const scale = scaleFor(
      { start_tick: 0, end_tick: 120 },
      { viewportHeight: 600, events, eventCount: 12, zoom: 4 },
    );
    const { cards, cursorY } = visibleScenes(storyOrder(events), scale, 60, {
      viewportHeight: 600,
    });
    const above = cards.filter((c) => c.scene.start_tick <= 60).map((c) => c.top);
    const below = cards.filter((c) => c.scene.start_tick > 60).map((c) => c.top);
    expect(above.length && below.length).toBeTruthy();
    expect(Math.max(...above) + CARD_HEIGHT).toBeLessThanOrEqual(cursorY + 1);
    expect(Math.min(...below)).toBeGreaterThanOrEqual(cursorY - 1);
  });

  it("keeps a scene on its side as the window moves", () => {
    const events = [scene("a", 0, 10), scene("b", 20, 30), scene("c", 40, 50)];
    const scale = scaleFor(
      { start_tick: 0, end_tick: 50 },
      { viewportHeight: 600, events, eventCount: 3, zoom: 4 },
    );
    const order = storyOrder(events);
    const sideAt = (tick: number) =>
      visibleScenes(order, scale, tick).cards.find((c) => c.scene.id === "b")?.side;
    expect([sideAt(20), sideAt(40)]).toEqual([1, 1]);
  });
});

describe("the travelling rule", () => {
  // Shaped like The Salt Road: many ticks, three scenes abreast at each.
  const events: RailScene[] = [];
  for (let n = 0, tick = 0; n < 33; n++, tick += 16)
    for (let lane = 0; lane < 3; lane++)
      events.push(scene(`t${tick}-${lane}`, tick, tick + 8));
  const bounds = { start_tick: 0, end_tick: events[events.length - 1]!.end_tick };
  const scale = scaleFor(bounds, {
    viewportHeight: 568,
    events,
    eventCount: events.length,
  });
  const order = storyOrder(events);
  const at = (tick: number) => {
    const { cards, cursorY, scrim } = visibleScenes(order, scale, tick, {
      viewportHeight: 568,
      columns: 2,
    });
    const tops = cards.map((c) => c.top);
    const bottoms = cards.map((c) => c.top + CARD_HEIGHT);
    return {
      rule: cursorY,
      drawn: cards.length,
      scrim,
      topCard: Math.min(...tops),
      blankAbove: Math.max(0, Math.min(...tops)),
      blankBelow: Math.max(0, 568 - Math.max(...bottoms)),
      ordered:
        cards
          .filter((c) => c.scene.start_tick <= tick)
          .every((c) => c.top + CARD_HEIGHT <= cursorY + 1) &&
        cards.filter((c) => c.scene.start_tick > tick).every((c) => c.top >= cursorY - 1),
    };
  };
  const middle = Math.round((scale.startTick + scale.endTick) / 2);

  it.each<[number]>([[0], [-80], [80]])(
    "stays in the middle through the body of the book (offset %i)",
    (offset) => {
      expect(at(middle + offset).rule).toBe(284);
    },
  );

  it("travels at both ends rather than leaving half the lens blank", () => {
    const opening = at(scale.startTick);
    const ending = at(scale.endTick);
    expect(opening.blankAbove).toBeLessThanOrEqual(24);
    expect(opening.rule).toBeLessThan(284);
    expect(ending.rule).toBeGreaterThan(284);
    expect(ending.blankBelow).toBeLessThanOrEqual(80);
    expect(opening.drawn).toBeGreaterThanOrEqual(at(middle).drawn - 2);
    expect(ending.drawn).toBeGreaterThanOrEqual(at(middle).drawn - 2);
  });

  it("never leaves the stage, and chronology always holds", () => {
    let lowest = 1e9;
    let highest = -1e9;
    let breaks = 0;
    for (let step = 0; step <= 200; step += 1) {
      const frame = at(tickAtScroll(scale, (step / 200) * scale.runHeight));
      lowest = Math.min(lowest, frame.rule);
      highest = Math.max(highest, frame.rule);
      if (!frame.ordered) breaks += 1;
    }
    expect({ lowest: lowest >= 20, highest: highest <= 548, breaks }).toEqual({
      lowest: true,
      highest: true,
      breaks: 0,
    });
  });

  it("paints no scrim over a parked card, and earns one where cards run off", () => {
    const opening = at(scale.startTick);
    const ending = at(scale.endTick);
    expect(opening.scrim.top).toBe(0);
    expect(ending.scrim.bottom).toBe(0);
    expect(opening.scrim.bottom).toBeGreaterThan(0.3);
    expect(ending.scrim.top).toBeGreaterThan(0.3);
  });

  it("parks the opening card clear of the stage border", () => {
    const { topCard } = at(scale.startTick);
    expect(topCard).toBeGreaterThanOrEqual(4);
    expect(topCard).toBeLessThanOrEqual(24);
  });

  it("centres a book too short to fill the lens", () => {
    const short = [scene("a", 0, 5), scene("b", 20, 25), scene("c", 40, 45)];
    const s = scaleFor(
      { start_tick: 0, end_tick: 45 },
      { viewportHeight: 568, events: short, eventCount: 3 },
    );
    const { cards, cursorY } = visibleScenes(storyOrder(short), s, 20, {
      viewportHeight: 568,
    });
    const above = Math.min(...cards.map((c) => c.top));
    const below = 568 - Math.max(...cards.map((c) => c.top + CARD_HEIGHT));
    expect(Math.abs(above - below)).toBeLessThanOrEqual(40);
    expect(cursorY).toBeGreaterThan(0);
  });
});

describe("empty stretches", () => {
  const events = [scene("departure", 0, 10), scene("terminus", 1000, 1010)];
  const scale = scaleFor(
    { start_tick: 0, end_tick: 1010 },
    { viewportHeight: 600, events, eventCount: 2 },
  );

  it("caps a huge gap and reports it as a break", () => {
    const gap = scale.map.gaps[0]!;
    expect(gap.rawDuration).toBe(990);
    expect(gap.displayDuration * scale.pixelsPerUnit).toBeCloseTo(140);
    expect(visibleBreaks(scale, 500, { viewportHeight: 600, overscan: 1000 })).toHaveLength(
      1,
    );
  });

  it.each<[number]>([[0], [10], [500], [1000], [1010]])(
    "stays invertible inside the gap at tick %i",
    (tick) => {
      expect(tickAtScroll(scale, scrollForTick(scale, tick))).toBe(tick);
    },
  );

  it("leaves ordinary gaps proportional", () => {
    const near = [scene("a", 0, 10), scene("b", 30, 40)];
    expect(
      scaleFor(
        { start_tick: 0, end_tick: 40 },
        { viewportHeight: 600, events: near, eventCount: 2 },
      ).map.gaps,
    ).toEqual([]);
  });

  it("counts scenes into density bins", () => {
    const bins = densityBins(events, scale, 4);
    expect(bins.reduce((a, b) => a + b, 0)).toBe(2);
    expect(bins[0]).toBe(1);
  });
});

describe("the book's own periods", () => {
  it.each<[string, RailScene[], { tick: number; level: number; label: string }[]]>([
    [
      "marks where each level turns over",
      [
        dated("a", 0, 5, ["Year 1", "Spring", "Week 1", "Day 1"]),
        dated("b", 10, 15, ["Year 1", "Spring", "Week 1", "Day 3"]),
        dated("c", 40, 45, ["Year 1", "Summer", "Week 1", "Day 1"]),
        dated("d", 90, 95, ["Year 2", "Spring", "Week 1", "Day 1"]),
      ],
      [
        { tick: 0, level: 0, label: "Year 1" },
        { tick: 0, level: 1, label: "Spring" },
        { tick: 40, level: 1, label: "Summer" },
        { tick: 90, level: 0, label: "Year 2" },
        { tick: 90, level: 1, label: "Spring" },
      ],
    ],
    [
      "bands only what is coarser than the finest pair",
      [
        dated("a", 0, 5, ["Year 1", "Spring", "Day 1"]),
        dated("b", 40, 45, ["Year 1", "Summer", "Day 1"]),
        dated("c", 90, 95, ["Year 2", "Spring", "Day 1"]),
      ],
      [
        { tick: 0, level: 0, label: "Year 1" },
        { tick: 90, level: 0, label: "Year 2" },
      ],
    ],
    [
      "gives a bare-tick book none",
      [dated("a", 0, 5, ["0"]), dated("b", 90, 95, ["90"])],
      [],
    ],
  ])("%s", (_, events, bands) => {
    expect(periodBands(storyOrder(events).ordered)).toEqual(bands);
  });

  const two = [
    dated("a", 0, 5, ["Year 1", "Spring", "Week 1", "Day 1"]),
    dated("d", 900, 905, ["Year 2", "Spring", "Week 1", "Day 1"]),
  ];
  const scale = scaleFor(
    { start_tick: 0, end_tick: 905 },
    { viewportHeight: 600, events: two, eventCount: 2 },
  );
  const bands = periodBands(storyOrder(two).ordered);

  it("draws levels turning over together as one boundary", () => {
    expect(
      visiblePeriods(bands, scale, 900, { viewportHeight: 600, overscan: 5000 }).map(
        (b) => ({ tick: b.tick, labels: b.labels }),
      ),
    ).toEqual([
      { tick: 0, labels: ["Year 1", "Spring"] },
      { tick: 900, labels: ["Year 2", "Spring"] },
    ]);
  });

  it("hangs each label away from the cursor, and still draws the one under it", () => {
    const at = (tick: number) =>
      visiblePeriods(bands, scale, tick, { viewportHeight: 600, overscan: 5000 }).map(
        (b) => [b.tick, b.side],
      );
    expect(at(0)).toContainEqual([0, "below"]);
    expect(at(900)).toContainEqual([900, "below"]);
    expect(at(900)).toContainEqual([0, "above"]);
  });

  it("does not draw bands off the stage", () => {
    const zoomed = scaleFor(
      { start_tick: 0, end_tick: 905 },
      { viewportHeight: 600, events: two, eventCount: 2, zoom: 8 },
    );
    expect(
      visiblePeriods(bands, zoomed, 900, { viewportHeight: 600 }).map((b) => b.tick),
    ).toEqual([900]);
  });
});

describe("display helpers", () => {
  const place = (id: string, tick: number): Placement<RailScene> => ({
    scene: scene(id, tick, tick + 1),
    side: 0,
    top: 0,
    anchorY: 39,
    endY: 39,
    opacity: 1,
  });

  it.each<[number, string[]]>([
    [2, ["a", "b", "c"]],
    [1, ["moment:0", "c"]],
  ])("groups same-tick scenes into a moment only in %i column(s)", (columns, keys) => {
    expect(
      displayPlacements([place("a", 0), place("b", 0), place("c", 5)], columns).map(
        (d) => d.key,
      ),
    ).toEqual(keys);
  });

  it("seeds the label with every tick the payload already dates", () => {
    expect(
      seedLabels([
        { ...scene("a", 0, 5), start_label: "Day 1", end_label: "Day 2" },
        scene("b", 9, 9),
      ]),
    ).toEqual([
      [0, "Day 1"],
      [5, "Day 2"],
    ]);
  });

  it.each<
    [
      { top: number; anchorY: number; endY: number },
      { anchor: number; durationHeight: number; stemHeight: number },
    ]
  >([
    [
      { top: 0, anchorY: 39, endY: 39 },
      { anchor: 39, durationHeight: 3, stemHeight: 2 },
    ],
    [
      { top: 100, anchorY: 120, endY: 180 },
      { anchor: 20, durationHeight: 60, stemHeight: 19 },
    ],
  ])("measures the rail furniture of %j", (placement, expected) => {
    expect(railGeometry(placement)).toMatchObject(expected);
  });
});
