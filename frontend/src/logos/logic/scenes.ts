// The scene strip above the page: every scene the volume's sections tell, in
// manuscript order, opened at this section's own -- so the writer can look at
// what the chapters either side of this one tell without leaving it.

import type {
  SceneChoice,
  SectionSummary,
  WriterScene,
  WriterSceneCards,
} from "../api/types";

export interface StripCard {
  key: string;
  section: SectionSummary;
  /** Null for the open section when it tells no scene yet: the card that offers to link one. */
  scene: WriterScene | null;
  side: "before" | "here" | "after";
  /** Its place among its own section's scenes: 1 of 2. */
  index: number;
  of: number;
}

export interface Track {
  cards: StripCard[];
  /** The open section's first card, where the strip starts. */
  start: number;
}

export function sceneTrack(
  data: WriterSceneCards,
  sections: SectionSummary[],
  current: string,
): Track {
  const byId = new Map(sections.map((section) => [section.id, section]));
  const cards: StripCard[] = [];
  let side: StripCard["side"] = "before";
  let start = 0;
  for (const row of data.sections) {
    const section = byId.get(row.section);
    if (!section) continue;
    const here = row.section === current;
    if (here) {
      side = "here";
      start = cards.length;
    }
    const scenes: (WriterScene | null)[] = row.scenes.length || !here ? row.scenes : [null];
    scenes.forEach((scene, index) =>
      cards.push({
        key: `${row.section}/${scene?.id ?? ""}/${index}`,
        section,
        scene,
        side,
        index: index + 1,
        of: scenes.length,
      }),
    );
    if (here) side = "after";
  }
  return { cards, start };
}

/** The scenes a section tells now, by id. */
export function sceneIds(data: WriterSceneCards, section: string): string[] {
  return (
    data.sections.find((row) => row.section === section)?.scenes.map((s) => s.id) ?? []
  );
}

/**
 * The order to save `picked` in: the ones the section already told keep their
 * places, and the rest follow in story order.
 */
export function chosenOrder(
  before: string[],
  picked: ReadonlySet<string>,
  choices: SceneChoice[],
): string[] {
  const kept = before.filter((id) => picked.has(id));
  const added = choices
    .map((choice) => choice.id)
    .filter((id) => picked.has(id) && !kept.includes(id));
  return [...kept, ...added];
}
