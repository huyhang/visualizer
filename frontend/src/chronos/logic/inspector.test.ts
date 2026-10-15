import {
  inspectorReducer,
  sameTarget,
  targetKey,
  type InspectorAction,
  type InspectorTarget,
} from "./inspector";

const scene: InspectorTarget = { kind: "scene", id: "dawn" };
const goal: InspectorTarget = { kind: "goal", id: "seal" };
const aldric: InspectorTarget = {
  kind: "article",
  ref: { database: "w", collection: "characters", id: "aldric" },
};

describe("inspectorReducer", () => {
  it.each<[string, InspectorTarget[], InspectorAction, InspectorTarget[]]>([
    ["open starts a fresh trail", [scene, aldric], { type: "open", target: goal }, [goal]],
    ["push follows a link", [scene], { type: "push", target: aldric }, [scene, aldric]],
    ["push onto nothing opens", [], { type: "push", target: goal }, [goal]],
    [
      "push of what is showing stays put",
      [scene, aldric],
      { type: "push", target: aldric },
      [scene, aldric],
    ],
    ["back unwinds one step", [scene, aldric], { type: "back" }, [scene]],
    ["back from nothing is nothing", [], { type: "back" }, []],
    ["close clears the trail", [scene, goal], { type: "close" }, []],
    [
      "forget takes a deleted record out, wherever it is",
      [scene, aldric, goal],
      { type: "forget", target: aldric },
      [scene, goal],
    ],
    [
      "forget of the one showing shows the one before",
      [scene, goal],
      { type: "forget", target: goal },
      [scene],
    ],
  ])("%s", (_, before, action, after) => {
    expect(inspectorReducer(before, action)).toEqual(after);
  });

  it.each<InspectorAction>([{ type: "close" }, { type: "back" }])(
    "answers %j on an empty trail with the same trail, so nothing re-renders",
    (action) => {
      const empty: InspectorTarget[] = [];
      expect(inspectorReducer(empty, action)).toBe(empty);
    },
  );

  it("answers forgetting what is not in the trail with the same trail", () => {
    const trail = [scene, goal];
    expect(inspectorReducer(trail, { type: "forget", target: aldric })).toBe(trail);
  });
});

describe("sameTarget", () => {
  it.each<[InspectorTarget, InspectorTarget, boolean]>([
    [scene, { kind: "scene", id: "dawn" }, true],
    [scene, { kind: "goal", id: "dawn" }, false],
    [
      aldric,
      { kind: "article", ref: { database: "w", collection: "characters", id: "aldric" } },
      true,
    ],
    [
      aldric,
      { kind: "article", ref: { database: "w", collection: "locations", id: "aldric" } },
      false,
    ],
  ])("%j vs %j", (a, b, expected) => {
    expect(sameTarget(a, b)).toBe(expected);
  });
});

describe("targetKey", () => {
  it.each<[InspectorTarget, string]>([
    [scene, "scene:dawn"],
    [aldric, "article:w/characters/aldric"],
  ])("keys %j", (target, expected) => {
    expect(targetKey(target)).toBe(expected);
  });
});
