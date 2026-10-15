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
  const ordered = readingOrder(manuscript);
  const direct = (volume) => ordered.find(
    (entry) => entry.volume.id === volume && entry.section.id === sectionId,
  ) || null;
  let found = direct(volumeId);
  if (found) return found;

  // A move keeps old bookmarks and URLs useful. Follow the short alias chain
  // until the section's current volume is found; a malformed cycle fails shut.
  const seen = new Set();
  let volume = volumeId;
  while (!seen.has(volume)) {
    seen.add(volume);
    const moved = (manuscript.section_aliases || []).find(
      (alias) => alias.source_volume === volume && alias.section === sectionId,
    );
    if (!moved) return null;
    volume = moved.target_volume;
    found = direct(volume);
    if (found) return found;
  }
  return null;
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

/**
 * Whether ``first`` names a strictly later section than ``second`` in book
 * order -- volumes in outline order, sections in theirs.
 *
 * Both arguments are `{volume, section}` ids rather than entries, because the
 * caller is comparing a saved mark against where the reader now is. An id this
 * manuscript no longer has is never ahead, so a section deleted out from under
 * a saved position can neither win the comparison nor lose it.
 */
export function sectionAhead(manuscript, first, second) {
  if (!first || !second) return false;
  const ordered = readingOrder(manuscript);
  const at = (spot) => ordered.findIndex(
    (entry) => entry.volume.id === spot.volume && entry.section.id === spot.section,
  );
  const here = at(first);
  const there = at(second);
  return here !== -1 && there !== -1 && here > there;
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

// What a link to a section may say: anything more (a review, the writing page)
// asks for a page of its own.
const SECTION_LINK_KEYS = new Set(["book", "volume", "section", "block", "draft"]);

/**
 * Where a link goes when it is another section of the book on screen, so the
 * reader can open it in place rather than load the whole page again: the
 * reader's own address (`home` on `origin`), naming `book`, a volume and a
 * section, and optionally a paragraph and a draft. Null for anything else,
 * which is the browser's to follow.
 */
export function sectionTarget(href, { origin, home, book }) {
  let url;
  try {
    url = new URL(href, origin);
  } catch {
    return null;
  }
  if (url.origin !== origin || url.pathname !== home) return null;
  const query = url.searchParams;
  if (!book || query.get("book") !== book) return null;
  const volume = query.get("volume");
  const section = query.get("section");
  if (!volume || !section) return null;
  for (const key of query.keys()) if (!SECTION_LINK_KEYS.has(key)) return null;
  return { volume, section, block: query.get("block"), draft: query.get("draft") };
}
