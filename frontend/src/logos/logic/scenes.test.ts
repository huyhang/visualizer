import type { SectionSummary, WriterScene, WriterSceneCards } from "../api/types";
import { chosenOrder, sceneIds, sceneTrack } from "./scenes";

const section = (id: string, number: number): SectionSummary => ({
  id,
  volume: "one",
  kind: "chapter",
  number,
  title: null,
  primary_draft_id: "draft-1",
  rev: 1,
});

const scene = (id: string): WriterScene => ({
  id,
  title: id,
  when: "",
  missing: false,
  description: "",
  place: null,
  cast: [],
  unseen: 0,
});

const SECTIONS = ["a", "b", "c", "d"].map((id, i) => section(id, i + 1));

const cards = (rows: Record<string, string[]>): WriterSceneCards => ({
  book: "ember",
  volume: "one",
  sections: Object.entries(rows).map(([id, scenes]) => ({
    section: id,
    scenes: scenes.map(scene),
  })),
});

const shape = (track: ReturnType<typeof sceneTrack>) =>
  track.cards.map(
    (card) => `${card.side}:${card.scene?.id ?? "-"}:${card.index}/${card.of}`,
  );

describe("the scene track", () => {
  it("runs through the volume in order, opening at this section's first scene", () => {
    const track = sceneTrack(
      cards({ a: ["s1"], b: ["s2", "s3"], c: [], d: ["s4"] }),
      SECTIONS,
      "b",
    );

    expect(shape(track)).toEqual([
      "before:s1:1/1",
      "here:s2:1/2",
      "here:s3:2/2",
      "after:s4:1/1",
    ]);
    expect(track.start).toBe(1);
  });

  it("holds a place for this section when it tells no scene, between its neighbours'", () => {
    const track = sceneTrack(cards({ a: ["s1"], b: [], c: ["s2"] }), SECTIONS, "b");

    expect(shape(track)).toEqual(["before:s1:1/1", "here:-:1/1", "after:s2:1/1"]);
    expect(track.start).toBe(1);
  });

  it("leaves out a section the manuscript no longer lists", () => {
    const track = sceneTrack(cards({ gone: ["s0"], a: ["s1"] }), SECTIONS, "a");

    expect(shape(track)).toEqual(["here:s1:1/1"]);
    expect(track.start).toBe(0);
  });

  it("reads the scenes a section tells now", () => {
    const data = cards({ a: ["s1", "s2"] });
    expect(sceneIds(data, "a")).toEqual(["s1", "s2"]);
    expect(sceneIds(data, "b")).toEqual([]);
  });
});

describe("choosing scenes", () => {
  const choices = ["early", "middle", "late"].map((id) => ({
    id,
    title: id,
    when: "",
    missing: false,
  }));

  it("keeps the ones already told in their places and adds the rest in story order", () => {
    expect(
      chosenOrder(["late", "early"], new Set(["late", "middle", "early"]), choices),
    ).toEqual(["late", "early", "middle"]);
  });

  it("lets go of the ones unticked, a scene Chronos no longer has among them", () => {
    expect(chosenOrder(["gone", "early"], new Set(["early"]), choices)).toEqual(["early"]);
    expect(chosenOrder(["gone"], new Set(["gone"]), choices)).toEqual(["gone"]);
  });
});
