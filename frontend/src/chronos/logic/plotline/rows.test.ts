import type { EventSummary, PlotlinePreview } from "../../api/types";
import { displayRows, remember } from "./rows";

const scene = (id: string, extra: Partial<EventSummary> = {}): EventSummary => ({
  id,
  title: id.toUpperCase(),
  scheduled: true,
  start_label: `Day ${id}`,
  ...extra,
});

const verdict: PlotlinePreview = {
  kind: "plotline-preview",
  id: "road",
  events: ["a", "b"],
  goals: [],
  effective_events: [
    scene("a", {
      findings: [{ code: "X", severity: "conflict", message: "m", events: [], refs: [] }],
    }),
    scene("b"),
    scene("t", { owned: false }),
  ],
  status: { conflicts: 1 },
};

describe("displayRows", () => {
  it("draws the verdict, numbering only the thread's own scenes", () => {
    const rows = displayRows(["a", "b"], verdict, new Map());
    expect(rows.map((r) => [r.id, r.index, r.owned])).toEqual([
      ["a", 0, true],
      ["b", 1, true],
      ["t", null, false],
    ]);
    expect(rows[0]?.scene.findings).toHaveLength(1);
  });

  it("draws the bare order, unjudged, while a verdict is on its way", () => {
    const known = new Map([
      [
        "b",
        scene("b", {
          findings: [{ code: "X", severity: "info", message: "m", events: [], refs: [] }],
          owned: false,
        }),
      ],
    ]);
    const rows = displayRows(["b", "new"], null, known);
    expect(
      rows.map((r) => [r.id, r.title, r.index, r.owned, r.scene.findings?.length]),
    ).toEqual([
      ["b", "B", 0, true, 0],
      ["new", "new", 1, true, 0],
    ]);
    expect(rows[1]?.when).toBe("unscheduled");
  });
});

describe("remember", () => {
  it("adds what it learns without forgetting what it knew", () => {
    const known = remember(new Map([["a", scene("a")]]), [
      { id: "a", title: "Renamed" },
      scene("b"),
    ]);
    expect(known.get("a")).toMatchObject({ title: "Renamed", start_label: "Day a" });
    expect([...known.keys()]).toEqual(["a", "b"]);
  });
});
