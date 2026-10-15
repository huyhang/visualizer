import { allScheduled, firstDiff, groupByPeriod, type TimedScene } from "./timeaxis";

const at = (parts: string[], end?: string[]): TimedScene & { id: string } => ({
  id: parts.join("|"),
  scheduled: true,
  start_tick: 0,
  end_tick: 1,
  start_label: parts.join(", "),
  start_parts: parts,
  end_label: end ? end.join(", ") : parts.join(", "),
  end_parts: end ?? parts,
});

describe("groupByPeriod", () => {
  it("nests years and months, leaving day and time on the scene", () => {
    const items = groupByPeriod([
      at(["Year 1", "Month 1", "Day 1", "00:00 AF"]),
      at(
        ["Year 1", "Month 1", "Day 3", "00:00 AF"],
        ["Year 1", "Month 1", "Day 4", "00:00 AF"],
      ),
      at(["Year 1", "Month 2", "Day 1", "08:00 AF"]),
    ]);
    expect(
      items.map((i) => (i.type === "header" ? `H${i.level}:${i.label}` : i.label)),
    ).toEqual([
      "H0:Year 1",
      "H1:Month 1",
      "Day 1, 00:00 AF",
      "Day 3, 00:00 AF → Day 4, 00:00 AF",
      "H1:Month 2",
      "Day 1, 08:00 AF",
    ]);
  });

  it.each<[string, TimedScene, string]>([
    ["an undated scene", { scheduled: false, start_label: null }, "unscheduled"],
    ["a flat calendar", at(["Day 3", "00:00"]), "Day 3, 00:00"],
    [
      "a span inside one day",
      at(["Day 3", "08:00"], ["Day 3", "18:00"]),
      "Day 3, 08:00 → 18:00",
    ],
  ])("labels %s", (_, scene, label) => {
    const rows = groupByPeriod([scene]).filter((i) => i.type === "event");
    expect(rows[0]?.label).toBe(label);
  });

  it("splits the label itself when an older response carries no parts", () => {
    const old: TimedScene = {
      scheduled: true,
      start_tick: 0,
      start_label: "Year 2, Day 5, 10:00",
    };
    expect(groupByPeriod([old]).map((i) => i.label)).toEqual(["Year 2", "Day 5, 10:00"]);
  });

  it("puts an undated scene under whatever period is current", () => {
    const items = groupByPeriod([
      at(["Year 1", "Month 1", "Day 1", "00:00"]),
      { scheduled: false },
    ]);
    expect(items.at(-1)).toMatchObject({ type: "event", label: "unscheduled", depth: 2 });
  });
});

describe("allScheduled", () => {
  it.each<[TimedScene[], boolean]>([
    [[], false],
    [[at(["Day 1", "00:00"])], true],
    [[at(["Day 1", "00:00"]), { scheduled: false }], false],
    [[{ scheduled: true, start_tick: 0, end_tick: null }], false],
  ])("%j", (events, expected) => {
    expect(allScheduled(events)).toBe(expected);
  });
});

describe("firstDiff", () => {
  it.each<[string[], string[], number]>([
    [[], [], 0],
    [["a", "b"], ["a", "c"], 1],
    [["a"], ["a", "b"], 1],
  ])("%j vs %j", (a, b, expected) => {
    expect(firstDiff(a, b)).toBe(expected);
  });
});
