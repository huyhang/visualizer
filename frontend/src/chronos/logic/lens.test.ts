import type { EntityRef, Plotline } from "../api/types";
import { castIndex, castList, refKey, sceneCast, scenesFeaturing } from "./lens";

const who = (id: string): EntityRef => ({ database: "w", collection: "characters", id });
const where = (id: string): EntityRef => ({ database: "w", collection: "locations", id });

function thread(id: string, scenes: [string, EntityRef[], EntityRef][]): Plotline {
  return {
    kind: "plotline",
    id,
    book: "b",
    events: [],
    goals: [],
    rev: 1,
    status: {},
    effective_events: scenes.map(([sid, characters, location]) => ({
      id: sid,
      characters,
      location,
    })),
  };
}

const road = thread("road", [
  ["departs", [who("aldric")], where("highkeep")],
  ["exchange", [who("aldric"), who("lyra")], where("emberport")],
]);
const shadow = thread("shadow", [
  ["infiltrates", [who("lyra")], where("emberport")],
  ["exchange", [who("aldric"), who("lyra")], where("emberport")],
]);

describe("castIndex", () => {
  it("reads each scene once, however many threads pass through it", () => {
    const index = castIndex([road, shadow]);
    expect([...index.keys()]).toEqual(["departs", "exchange", "infiltrates"]);
    expect(index.get("exchange")?.map((r) => r.id)).toEqual([
      "aldric",
      "lyra",
      "emberport",
    ]);
  });

  it("skips a thread that was not expanded", () => {
    const bare = { ...road, effective_events: ["departs"] };
    expect(castIndex([bare]).size).toBe(0);
  });
});

describe("scenesFeaturing", () => {
  const index = castIndex([road, shadow]);
  it.each<[EntityRef, string[]]>([
    [who("aldric"), ["departs", "exchange"]],
    [who("lyra"), ["exchange", "infiltrates"]],
    [where("emberport"), ["exchange", "infiltrates"]],
    [who("nobody"), []],
    [{ ...who("aldric"), database: "other" }, []],
  ])("finds where %j appears", (ref, scenes) => {
    expect([...scenesFeaturing(index, ref)].sort()).toEqual(scenes);
  });
});

describe("castList", () => {
  it("puts people first, then places, each by how often they appear", () => {
    const list = castList(castIndex([road, shadow]));
    expect(list.map((m) => `${m.ref.id}:${m.scenes}`)).toEqual([
      "aldric:2",
      "lyra:2",
      "emberport:2",
      "highkeep:1",
    ]);
  });

  it("counts someone named twice in one scene once", () => {
    const twice = thread("t", [["s", [who("aldric"), who("aldric")], where("x")]]);
    expect(castList(castIndex([twice]))[0]).toEqual({ ref: who("aldric"), scenes: 1 });
  });
});

describe("helpers", () => {
  it("keys a ref by world, kind and id", () => {
    expect(refKey(who("aldric"))).toBe("w/characters/aldric");
  });

  it("lists a scene's people, place and things in that order", () => {
    const item = { database: "w", collection: "items", id: "seal" };
    expect(
      sceneCast({ characters: [who("a")], location: where("x"), items: [item] }),
    ).toEqual([who("a"), where("x"), item]);
  });
});
