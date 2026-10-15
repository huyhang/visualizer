import {
  canRedo,
  canUndo,
  record,
  redo,
  sameList,
  startHistory,
  undo,
  type History,
} from "./history";

const h = <T>(past: T[], present: T, future: T[]): History<T> => ({
  past,
  present,
  future,
});

describe("history", () => {
  it.each<
    [string, (x: History<number>) => History<number>, History<number>, History<number>]
  >([
    [
      "record pushes the present into the past",
      (x) => record(x, 3),
      h([1], 2, []),
      h([1, 2], 3, []),
    ],
    [
      "record forgets what was undone",
      (x) => record(x, 9),
      h([1], 2, [3, 4]),
      h([1, 2], 9, []),
    ],
    [
      "record of the same value changes nothing",
      (x) => record(x, 2),
      h([1], 2, [3]),
      h([1], 2, [3]),
    ],
    ["undo steps back", undo, h([1, 2], 3, []), h([1], 2, [3])],
    ["undo with no past stays", undo, h([], 1, [2]), h([], 1, [2])],
    ["redo steps forward", redo, h([1], 2, [3, 4]), h([1, 2], 3, [4])],
    ["redo with no future stays", redo, h([1], 2, []), h([1], 2, [])],
  ])("%s", (_, act, before, after) => {
    expect(act(before)).toEqual(after);
  });

  it("round-trips through undo and redo", () => {
    let x = startHistory(["a"]);
    x = record(x, ["a", "b"], sameList);
    x = record(x, ["b", "a"], sameList);
    expect(undo(undo(x)).present).toEqual(["a"]);
    expect(redo(undo(x)).present).toEqual(["b", "a"]);
  });

  it("treats an equal list as no change when told how to compare", () => {
    const x = startHistory(["a", "b"]);
    expect(record(x, ["a", "b"], sameList)).toBe(x);
    expect(record(x, ["a", "b"])).not.toBe(x);
  });

  it.each<[History<number>, boolean, boolean]>([
    [h([], 1, []), false, false],
    [h([0], 1, []), true, false],
    [h([], 1, [2]), false, true],
  ])("knows whether it can undo or redo %j", (x, u, r) => {
    expect(canUndo(x)).toBe(u);
    expect(canRedo(x)).toBe(r);
  });
});
