import { fourThreads } from "./testGraphs";
import {
  footnote,
  initialSelection,
  inverted,
  matchesFilter,
  threadsByNode,
  toggled,
  urlSelection,
} from "./selection";

const BOOK = ["alpha", "gamma", "beta", "delta"];
const set = (...ids: string[]) => new Set(ids);

describe("initialSelection", () => {
  it.each<[string, string[], string | null, string[]]>([
    ["everything when nothing is asked", [], null, BOOK],
    ["what the URL lists", ["beta", "delta"], null, ["beta", "delta"]],
    ["what the URL lists that still exists", ["beta", "gone"], null, ["beta"]],
    ["everything when the URL names only ghosts", ["gone"], null, BOOK],
    ["the connected preset over the URL", ["delta"], "alpha", ["alpha", "beta"]],
    ["the URL when the preset's thread is gone", ["delta"], "gone", ["delta"]],
  ])("opens on %s", (_, selection, connectedFrom, expected) => {
    expect([...initialSelection(fourThreads(), selection, connectedFrom)].sort()).toEqual(
      [...expected].sort(),
    );
  });
});

describe("changing the selection", () => {
  it.each<[Set<string>, string, string[]]>([
    [set("alpha"), "beta", ["alpha", "beta"]],
    [set("alpha", "beta"), "beta", ["alpha"]],
  ])("toggles %j by %s", (before, id, after) => {
    expect([...toggled(before, id)].sort()).toEqual(after);
  });

  it("inverts in book order", () => {
    expect([...inverted(BOOK, set("alpha", "delta"))]).toEqual(["gamma", "beta"]);
  });

  it.each<[Set<string>, string[]]>([
    [set(...BOOK), []],
    [set("delta", "alpha"), ["alpha", "delta"]],
    [set(), []],
  ])("writes %j to the URL as %j", (selected, expected) => {
    expect(urlSelection(BOOK, selected)).toEqual(expected);
  });
});

describe("matchesFilter", () => {
  it.each<[string, string, boolean]>([
    ["The Knight's Road", "", true],
    ["The Knight's Road", "road knight", true],
    ["The Knight's Road", "ROAD", true],
    ["The Knight's Road", "road spy", false],
  ])("%j against %j", (title, query, expected) => {
    expect(matchesFilter(title, query)).toBe(expected);
  });
});

describe("threadsByNode", () => {
  it("knows every thread through a shared scene", () => {
    const by = threadsByNode(fourThreads().plotlines);
    expect([...(by.get("j1") ?? [])].sort()).toEqual(["alpha", "beta"]);
    expect([...(by.get("T") ?? [])].sort()).toEqual(["alpha", "beta", "delta", "gamma"]);
  });
});

describe("footnote", () => {
  it.each<[Parameters<typeof footnote>[0], string]>([
    [{ folded: 0, hidden: 0, hasTerminus: false, hasUnscheduled: false }, ""],
    [
      { folded: 1, hidden: 4, hasTerminus: false, hasUnscheduled: false },
      "4 scenes are folded into 1 solitary stretch — unfold one to see them.",
    ],
    [
      { folded: 2, hidden: 7, hasTerminus: true, hasUnscheduled: false },
      "7 scenes are folded into 2 solitary stretches — unfold one to see them. The underlined scene is this book's ending — every thread must reach it.",
    ],
  ])("says %j", (facts, expected) => {
    expect(footnote(facts)).toBe(expected);
  });
});
