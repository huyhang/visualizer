import type { EntityRef } from "../api/types";
import { castIndex, castList, refKey, scenesFeaturing } from "./lens";

const who = (id: string): EntityRef => ({ database: "w", collection: "characters", id });
const where = (id: string): EntityRef => ({ database: "w", collection: "locations", id });

/** A scene as the listing gives it: its place first, then its cast. */
const scene = (id: string, place: EntityRef, ...people: EntityRef[]) => ({
  id,
  cast: [place, ...people],
});

const scenes = [
  scene("departs", where("highkeep"), who("aldric")),
  scene("exchange", where("emberport"), who("aldric"), who("lyra")),
  scene("infiltrates", where("emberport"), who("lyra")),
];

describe("castIndex", () => {
  it("indexes every scene in the listing, on a thread or not", () => {
    const index = castIndex([...scenes, scene("aside", where("highkeep"), who("aldric"))]);
    expect([...index.keys()]).toEqual(["departs", "exchange", "infiltrates", "aside"]);
    expect(index.get("exchange")?.map((r) => r.id)).toEqual([
      "emberport",
      "aldric",
      "lyra",
    ]);
  });

  it("takes a row without a cast, from an older server, as nobody's", () => {
    expect(castIndex([{ id: "bare" }]).get("bare")).toEqual([]);
  });
});

describe("scenesFeaturing", () => {
  const index = castIndex(scenes);
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
    const list = castList(castIndex(scenes));
    expect(list.map((m) => `${m.ref.id}:${m.scenes}`)).toEqual([
      "aldric:2",
      "lyra:2",
      "emberport:2",
      "highkeep:1",
    ]);
  });

  it("counts someone named twice in one scene once", () => {
    const twice = scene("s", where("x"), who("aldric"), who("aldric"));
    expect(castList(castIndex([twice]))[0]).toEqual({ ref: who("aldric"), scenes: 1 });
  });
});

describe("helpers", () => {
  it("keys a ref by world, kind and id", () => {
    expect(refKey(who("aldric"))).toBe("w/characters/aldric");
  });
});
