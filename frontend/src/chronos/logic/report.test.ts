import type { BookReport, Issue, IssueGroup } from "../api/types";
import { withTitles } from "./findings";
import {
  count,
  homeThread,
  issueKey,
  keepPlace,
  narrow,
  readingOrder,
  rollup,
  step,
  verdict,
} from "./report";

function issue(code: string, scene: string | null, plotlines: string[] = []): Issue {
  return {
    code,
    severity: "conflict",
    message: `${code} at ${scene}`,
    scene: scene ? { id: scene, title: scene } : null,
    events: [],
    plotlines: plotlines.map((id) => ({ id, title: id })),
    refs: [],
    goal: null,
    goals: [],
  };
}

const group = (
  title: string,
  issues: Issue[],
  severity: "conflict" | "info" = "conflict",
): IssueGroup => ({
  title,
  severity,
  codes: [...new Set(issues.map((i) => i.code))],
  issues,
});

const clash = issue("TEMPORAL_CONFLICT", "dawn", ["road", "tale"]);
const order = issue("ORDERING_VIOLATION", "harbor", ["tale"]);
const ending = issue("NO_TERMINUS", null);
const undated = issue("UNSCHEDULED", "later", ["road"]);
const PROBLEMS = [
  group("Two places", [clash]),
  group("Out of order", [order]),
  group("No ending", [ending]),
];
const NOTES = [group("Waiting", [undated], "info")];

describe("narrow", () => {
  it.each<[string, string, number[]]>([
    ["all threads", "", [1, 1, 1]],
    ["one thread keeps what lands on it", "tale", [1, 1]],
    ["another thread", "road", [1]],
    ["a thread with nothing", "nowhere", []],
  ])("to %s", (_, thread, sizes) => {
    expect(narrow(PROBLEMS, thread).map((g) => g.issues.length)).toEqual(sizes);
  });
});

describe("counting", () => {
  it("counts every issue, or those it is asked to keep", () => {
    expect(count(PROBLEMS)).toBe(3);
    expect(count(PROBLEMS, (i) => i.scene !== null)).toBe(2);
  });

  it.each<[string, IssueGroup[], IssueGroup[], { problems: number; undated: number }]>([
    ["a book with both", PROBLEMS, NOTES, { problems: 3, undated: 1 }],
    ["a sound book", [], [], { problems: 0, undated: 0 }],
    [
      "notes that are not undated scenes",
      [],
      [group("Goals", [issue("GOAL_UNACHIEVED", null)], "info")],
      { problems: 0, undated: 0 },
    ],
  ])("reads the verdict of %s", (_, problems, notes, expected) => {
    expect(verdict(problems, notes)).toEqual(expected);
  });
});

describe("triage", () => {
  it.each<[boolean, string[]]>([
    [true, ["TEMPORAL_CONFLICT", "ORDERING_VIOLATION", "NO_TERMINUS", "UNSCHEDULED"]],
    [false, ["TEMPORAL_CONFLICT", "ORDERING_VIOLATION", "NO_TERMINUS"]],
  ])("walks problems then notes (notes open: %s)", (open, codes) => {
    expect(readingOrder(PROBLEMS, NOTES, open).map((i) => i.code)).toEqual(codes);
  });

  it("tells two issues apart by what they are about", () => {
    expect(issueKey(clash)).not.toBe(issueKey(order));
    expect(issueKey(clash)).toBe(issueKey({ ...clash, message: "reworded" }));
  });

  it.each<[string, Issue[], string | null, number, number]>([
    ["the same issue where it moved to", [order, clash], issueKey(clash), 0, 1],
    ["the next one up when it was fixed", [order, ending], issueKey(clash), 0, 0],
    ["the last one when the fixed one was last", [clash], issueKey(ending), 2, 0],
    ["nothing when nothing is left", [], issueKey(clash), 0, -1],
    ["the first when nothing was chosen", [clash, order], null, -1, 0],
  ])("keeps its place: %s", (_, list, key, index, expected) => {
    expect(keepPlace(list, key, index)).toBe(expected);
  });

  it.each<[number, number, number, number]>([
    [0, 1, 3, 1],
    [2, 1, 3, 2],
    [0, -1, 3, 0],
    [-1, 1, 3, 0],
    [0, 1, 0, -1],
  ])("steps from %i by %i through %i", (index, delta, length, expected) => {
    expect(step(index, delta, length)).toBe(expected);
  });

  it("opens an issue on the first thread it lands on", () => {
    expect(homeThread(clash)).toBe("road");
    expect(homeThread(ending)).toBeNull();
  });
});

describe("rollup", () => {
  it("puts the most troubled thread first and breaks ties by title", () => {
    const report = {
      plotlines: [
        { id: "c", title: "Gamma", problems: 1 },
        { id: "a", title: "Alpha", problems: 0 },
        { id: "b", title: "Beta", problems: 1 },
      ],
    } as BookReport;
    expect(rollup(report).map((p) => p.id)).toEqual(["b", "c", "a"]);
  });
});

describe("withTitles", () => {
  it.each<[string, [string, string][], string]>([
    ["'aldric' cannot be here", [["aldric", "Sir Aldric"]], "'Sir Aldric' cannot be here"],
    [
      "'aldric' and 'aldric-the-younger'",
      [["aldric", "Sir Aldric"]],
      "'Sir Aldric' and 'aldric-the-younger'",
    ],
    ["'lyra' unread", [["lyra", "lyra"]], "'lyra' unread"],
    ["no quotes aldric", [["aldric", "Sir Aldric"]], "no quotes aldric"],
  ])("rewrites %j", (message, titles, expected) => {
    expect(withTitles(message, new Map(titles))).toBe(expected);
  });
});
