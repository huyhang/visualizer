// Ported from tests/chronos/test_cursor_label_js.py.

import { tickLabels } from "./cursorLabel";

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function harness({
  seeded = [] as [number, string][],
  answer = (t: number): string => `Day ${t}`,
  delay = 0,
  minGap = 0,
} = {}) {
  const asked: number[] = [];
  const written: string[] = [];
  let inFlight = 0;
  let peak = 0;
  const reading = tickLabels({
    seeded,
    minGap,
    onLabel: (text) => written.push(text),
    formatTick: async (tick) => {
      asked.push(tick);
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      try {
        if (delay) await sleep(delay);
        return answer(tick);
      } finally {
        inFlight -= 1;
      }
    },
  });
  return { reading, asked, written, peak: () => peak };
}

describe("tickLabels", () => {
  it("dates a seeded tick without asking anyone", async () => {
    const h = harness({
      seeded: [
        [10, "Day 1"],
        [20, "Day 2"],
      ],
    });
    h.reading.cursorAt(10);
    h.reading.cursorAt(20);
    await sleep(20);
    expect({ written: h.written, asked: h.asked }).toEqual({
      written: ["Day 1", "Day 2"],
      asked: [],
    });
  });

  it("never falls back to a tick once a date is known", async () => {
    const h = harness({ seeded: [[10, "Day 1"]], delay: 30 });
    h.reading.cursorAt(10);
    h.reading.cursorAt(11);
    const midScroll = [...h.written];
    await sleep(80);
    expect(midScroll).toEqual(["Day 1"]);
    expect(h.written).toEqual(["Day 1", "Day 11"]);
  });

  it("shows the tick on a label that has never had a date", async () => {
    const h = harness({ delay: 30 });
    h.reading.cursorAt(7);
    const before = [...h.written];
    await sleep(80);
    expect(before).toEqual(["Tick 7"]);
    expect(h.written).toEqual(["Tick 7", "Day 7"]);
  });

  it("keeps only one request in flight, collapsing a scroll", async () => {
    const h = harness({ delay: 20 });
    for (let tick = 0; tick < 40; tick += 1) h.reading.cursorAt(tick);
    await sleep(200);
    expect(h.peak()).toBe(1);
    expect(h.asked.length).toBeLessThan(40);
  });

  it("chases the cursor rather than the backlog", async () => {
    const h = harness({ delay: 20 });
    [1, 2, 3, 4].forEach((t) => h.reading.cursorAt(t));
    await sleep(200);
    expect(h.asked).toEqual([1, 4]);
    expect(h.written.at(-1)).toBe("Day 4");
    expect(h.written).not.toContain("Day 1");
  });

  it("does not display an answer for a tick the cursor has left", async () => {
    const h = harness({ seeded: [[9, "Day 9"]], delay: 40 });
    h.reading.cursorAt(1);
    await sleep(10);
    h.reading.cursorAt(9);
    await sleep(120);
    expect(h.written.at(-1)).toBe("Day 9");
  });

  it("never asks twice for ground already covered", async () => {
    const h = harness({ delay: 10 });
    for (const tick of [5, 6, 5]) {
      h.reading.cursorAt(tick);
      await sleep(60);
    }
    expect(h.asked).toEqual([5, 6]);
    expect(h.written.at(-1)).toBe("Day 5");
  });

  it("spaces lookups by the rate floor", async () => {
    const h = harness({ minGap: 40 });
    const started = Date.now();
    for (let step = 0; step < 40; step += 1) {
      h.reading.cursorAt(100 + step);
      await sleep(5);
    }
    await sleep(80);
    const elapsed = Date.now() - started;
    expect(h.asked.length).toBeLessThanOrEqual(1 + Math.floor(elapsed / 40));
    expect(h.asked.length).toBeGreaterThanOrEqual(2);
  });

  it("leaves the reading alone when a lookup fails", async () => {
    const h = harness({
      seeded: [[10, "Day 1"]],
      answer: (tick) => {
        if (tick === 11) throw new Error("no");
        return `Day ${tick}`;
      },
    });
    h.reading.cursorAt(10);
    h.reading.cursorAt(11);
    await sleep(40);
    h.reading.cursorAt(12);
    await sleep(40);
    expect(h.written).toEqual(["Day 1", "Day 12"]);
  });

  it("writes nothing to a stopped label", async () => {
    const h = harness({ seeded: [[10, "Day 1"]], delay: 30 });
    h.reading.cursorAt(10);
    h.reading.cursorAt(11);
    h.reading.stop();
    await sleep(80);
    expect(h.written).toEqual(["Day 1"]);
  });
});
