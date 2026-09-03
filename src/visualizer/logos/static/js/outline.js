// Pure book-outline rules shared by the contents page and the reader's jump
// dialog. The DOM only has to render the result; search semantics live here.

import { findSection, sectionLabel, sectionName } from "./navigation.js";

export const SECTION_PAGE_SIZE = 25;

const terms = (query) => String(query || "")
  .trim()
  .toLocaleLowerCase()
  .split(/\s+/)
  .filter(Boolean);

function matches(volume, section, wanted) {
  const text = [
    volume.title,
    `volume ${volume.number}`,
    sectionName(section),
    sectionLabel(section),
    section.kind,
  ].filter(Boolean).join(" ").toLocaleLowerCase();
  return wanted.every((term) => text.includes(term));
}

export function filterOutline(manuscript, query) {
  const wanted = terms(query);
  return (manuscript.volumes || []).map((volume) => ({
    ...volume,
    sections: wanted.length
      ? (volume.sections || []).filter((section) => matches(volume, section, wanted))
      : [...(volume.sections || [])],
  })).filter((volume) => !wanted.length || volume.sections.length);
}

export function sectionCount(volumes) {
  return volumes.reduce(
    (total, volume) => total + (volume.sections || []).length, 0,
  );
}

export function pageForSection(sections, sectionId, pageSize = SECTION_PAGE_SIZE) {
  const at = (sections || []).findIndex((section) => section.id === sectionId);
  return at < 0 ? 0 : Math.floor(at / pageSize);
}

export function sectionPage(sections, requested, pageSize = SECTION_PAGE_SIZE) {
  const all = sections || [];
  const pages = Math.ceil(all.length / pageSize);
  const wanted = Number.isInteger(requested) ? requested : 0;
  const page = pages ? Math.min(Math.max(0, wanted), pages - 1) : 0;
  const start = page * pageSize;
  const end = Math.min(start + pageSize, all.length);
  return {
    page,
    pages,
    start,
    end,
    total: all.length,
    sections: all.slice(start, end),
  };
}

export function defaultOpenVolume(manuscript, position) {
  if (position) {
    const resumed = findSection(manuscript, position.volume, position.section);
    if (resumed) return resumed.volume.id;
  }
  return manuscript.volumes?.[0]?.id || null;
}
