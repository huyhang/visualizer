import {
  LANE_PALETTE,
  paletteColor,
  paletteDash,
  paletteTurn,
  threadPaints,
} from "./threadColors";

describe("palette", () => {
  it.each<[number, string, number, string]>([
    [0, LANE_PALETTE[0], 0, ""],
    [11, LANE_PALETTE[11], 0, ""],
    [12, LANE_PALETTE[0], 1, "7 4"],
    [25, LANE_PALETTE[1], 2, "2 4"],
    [36, LANE_PALETTE[0], 0, ""],
    [-1, LANE_PALETTE[11], 0, ""],
  ])("thread %i wears its colour and stroke", (n, color, turn, dash) => {
    expect(paletteColor(n)).toBe(color);
    expect(paletteTurn(n)).toBe(turn);
    expect(paletteDash(n)).toBe(dash);
  });
});

describe("threadPaints", () => {
  it("keys colour to a thread's place in the whole book, not the order given", () => {
    const a = threadPaints(["road", "gambit", "shadow"]);
    const b = threadPaints(["shadow", "road", "gambit"]);
    expect(a).toEqual(b);
    expect(a.get("gambit")?.color).toBe(LANE_PALETTE[0]);
    expect(a.get("shadow")?.color).toBe(LANE_PALETTE[2]);
  });

  it("counts a repeated id once", () => {
    expect(threadPaints(["a", "a", "b"]).get("b")?.color).toBe(LANE_PALETTE[1]);
  });
});
