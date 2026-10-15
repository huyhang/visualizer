// Naming sections and finding them: the outline's pure rules, shared with the
// reader's (`static/js/navigation.js`, `outline.js`, `contents.js`).

import type { Manuscript, SectionSummary, VolumeSummary } from "../api/types";

/** What kind of section this is: "Chapter 4", "Prologue", "Glossary". */
export function sectionLabel(section: Pick<SectionSummary, "kind" | "number">): string {
  if (section.kind === "chapter") return `Chapter ${section.number ?? ""}`.trim();
  return section.kind.charAt(0).toUpperCase() + section.kind.slice(1);
}

/** A section's title, or its kind when it has none. */
export function sectionName(
  section: Pick<SectionSummary, "kind" | "number" | "title">,
): string {
  return section.title || sectionLabel(section);
}

const terms = (query: string) =>
  query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);

/** The outline narrowed to sections matching every word of `query`. */
export function filterOutline(manuscript: Manuscript, query: string): VolumeSummary[] {
  const wanted = terms(query);
  if (!wanted.length) return manuscript.volumes;
  return manuscript.volumes
    .map((volume) => ({
      ...volume,
      sections: volume.sections.filter((section) => {
        const text = [
          volume.title,
          `volume ${volume.number}`,
          sectionName(section),
          sectionLabel(section),
          section.kind,
        ]
          .join(" ")
          .toLocaleLowerCase();
        return wanted.every((term) => text.includes(term));
      }),
    }))
    .filter((volume) => volume.sections.length);
}

export function allSectionIds(manuscript: Manuscript): Set<string> {
  return new Set(
    manuscript.volumes.flatMap((volume) => volume.sections.map((section) => section.id)),
  );
}

/** A section id from a title, not yet taken in `known`. */
export function availableId(title: string, known: Set<string>, fallback: string): string {
  const stem =
    title
      .toLowerCase()
      .normalize("NFKD")
      // Accents off rather than turned into hyphens: "Île" is "ile", not "i-le".
      .replace(/\p{M}/gu, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || fallback;
  let candidate = stem;
  for (let suffix = 2; known.has(candidate); suffix += 1) candidate = `${stem}-${suffix}`;
  return candidate;
}

export interface Located {
  volume: VolumeSummary;
  section: SectionSummary;
}

/** The section at `volumeId`/`sectionId`, following move aliases to where it lives now. */
export function findSection(
  manuscript: Manuscript,
  volumeId: string,
  sectionId: string,
): Located | null {
  const direct = (volumeIdNow: string): Located | null => {
    const volume = manuscript.volumes.find((v) => v.id === volumeIdNow);
    const section = volume?.sections.find((s) => s.id === sectionId);
    return volume && section ? { volume, section } : null;
  };
  const seen = new Set<string>();
  let at = volumeId;
  while (!seen.has(at)) {
    const found = direct(at);
    if (found) return found;
    seen.add(at);
    const moved = (manuscript.section_aliases ?? []).find(
      (alias) => alias.source_volume === at && alias.section === sectionId,
    );
    if (!moved) return null;
    at = moved.target_volume;
  }
  return null;
}
