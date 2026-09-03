// Where you are in an ordered list, and what to call the thing you are on.
//
// Pure, so the two pagers -- one across volumes, one across the sections of a
// volume -- share the same answer instead of each doing their own `findIndex`
// arithmetic, and so pytest can check the ends of the list without a browser.
// Off-by-one at a boundary is the classic bug here: a "next" link on the last
// section that reloads the same section reads as the reader being broken.

/** The entries either side of ``id``; null at each end, and for an unknown id. */
export function neighbours(items, id) {
  const at = (items || []).findIndex((item) => item.id === id);
  if (at === -1) return { previous: null, next: null };
  return {
    previous: items[at - 1] || null,
    next: items[at + 1] || null,
  };
}

/** One ordered list of section entries, with their parent volume attached. */
export function readingOrder(manuscript) {
  return (manuscript.volumes || []).flatMap((volume) =>
    (volume.sections || []).map((section) => ({ section, volume })),
  );
}

export function findSection(manuscript, volumeId, sectionId) {
  return readingOrder(manuscript).find(
    (entry) => entry.volume.id === volumeId && entry.section.id === sectionId,
  ) || null;
}

/** Previous and next sections in book order, including volume boundaries. */
export function sectionNeighbours(manuscript, volumeId, sectionId) {
  const ordered = readingOrder(manuscript);
  const at = ordered.findIndex(
    (entry) => entry.volume.id === volumeId && entry.section.id === sectionId,
  );
  if (at === -1) return { previous: null, next: null };
  return {
    previous: ordered[at - 1] || null,
    next: ordered[at + 1] || null,
  };
}

/** What kind of section this is: "Chapter 4", "Prologue", "Glossary". */
export function sectionLabel(section) {
  if (section.kind === "chapter") return `Chapter ${section.number}`;
  return section.kind.charAt(0).toUpperCase() + section.kind.slice(1);
}

/**
 * What to show a reader.
 *
 * A section's title is optional -- prologues and glossaries usually have
 * none -- so an untitled one is named by its kind rather than left blank in
 * the contents and in every heading.
 */
export function sectionName(section) {
  return section.title || sectionLabel(section);
}
