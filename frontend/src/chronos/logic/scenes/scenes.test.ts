import type { EntityRef, SceneEvent } from "../../api/types";
import {
  afterInUse,
  candidateIds,
  createAtFreeId,
  emptiedBy,
  firstStep,
  type ThreadInWay,
} from "./deletion";
import { bareRef, collectionOptions, pick, unpick, type RefRole } from "./refs";

const who = (id: string): EntityRef => ({ database: "w", collection: "characters", id });
const event = {
  kind: "event",
  id: "dawn",
  book: "b",
  rev: 3,
  location: who("x"),
} as SceneEvent;
const thread = (id: string, events: string[]): ThreadInWay => ({ id, title: id, events });

describe("collectionOptions", () => {
  it.each<[string[], RefRole, string[]]>([
    [[], "location", ["locations"]],
    [["characters", "items", "locations"], "characters", ["characters"]],
    [["characters", "people", "locations"], "characters", ["characters", "people"]],
    [["realms"], "location", ["locations", "realms"]],
  ])("from %j for %s", (observed, role, expected) => {
    expect(collectionOptions(observed, role)).toEqual(expected);
  });
});

describe("pick", () => {
  it.each<[string, EntityRef[], EntityRef, boolean, string[]]>([
    ["a place replaces the place", [who("a")], who("b"), false, ["b"]],
    ["a cast member joins", [who("a")], who("b"), true, ["a", "b"]],
    ["someone already there is not added twice", [who("a")], who("a"), true, ["a"]],
  ])("%s", (_, chosen, ref, multiple, expected) => {
    expect(pick(chosen, ref, multiple).map((r) => r.id)).toEqual(expected);
  });

  it("removes exactly the one ref", () => {
    expect(unpick([who("a"), who("b")], who("a")).map((r) => r.id)).toEqual(["b"]);
  });

  it("strips a picked result down to a reference", () => {
    expect(bareRef({ ...who("a"), title: "A" } as EntityRef)).toEqual(who("a"));
  });
});

describe("deleting", () => {
  it.each<[string | null, string]>([
    ["dawn", "terminus"],
    ["dusk", "confirm"],
    [null, "confirm"],
  ])("starts with the terminus %j at %s", (terminus, kind) => {
    expect(firstStep(event, terminus).kind).toBe(kind);
  });

  it.each<[ThreadInWay[], string[]]>([
    [[thread("road", ["dawn"]), thread("tale", ["dawn", "dusk"])], ["road"]],
    [[thread("tale", ["dawn", "dusk"])], []],
    [[thread("other", ["dusk"])], []],
  ])("finds the threads it would empty in %j", (threads, emptied) => {
    expect(emptiedBy(threads, "dawn").map((t) => t.id)).toEqual(emptied);
  });

  it.each<[ThreadInWay[], string]>([
    [[thread("tale", ["dawn", "dusk"])], "detach"],
    [[thread("road", ["dawn"])], "would-empty"],
  ])("answers EVENT_IN_USE over %j with %s", (threads, kind) => {
    expect(afterInUse(event, threads).kind).toBe(kind);
  });
});

describe("free ids", () => {
  it("tries the id, then numbered suffixes", () => {
    expect(candidateIds("harbor", 3)).toEqual(["harbor", "harbor-2", "harbor-3"]);
  });

  it.each<[string[], string]>([
    [[], "harbor"],
    [["harbor"], "harbor-2"],
    [["harbor", "harbor-2"], "harbor-3"],
  ])("creates past %j at %s", async (taken, expected) => {
    const create = async (id: string) => {
      if (taken.includes(id)) throw new Error("taken");
      return id;
    };
    await expect(createAtFreeId("harbor", create, () => true)).resolves.toBe(expected);
  });

  it("passes on any other refusal", async () => {
    const create = async () => {
      throw new Error("forbidden");
    };
    await expect(createAtFreeId("harbor", create, () => false)).rejects.toThrow(
      "forbidden",
    );
  });

  it("gives up after its attempts", async () => {
    const create = async () => {
      throw new Error("taken");
    };
    await expect(createAtFreeId("h", create, () => true, 2)).rejects.toThrow(
      "Could not find a free id starting from 'h'.",
    );
  });
});
