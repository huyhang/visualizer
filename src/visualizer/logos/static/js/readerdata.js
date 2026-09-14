// Pure selectors for the private reader layer. DOM rendering and persistence
// stay with the caller; these rules are independently testable.

export function dataForSection(items, volume, section, draft = null) {
  const all = Array.isArray(items) ? items : [];
  const onDraft = (item) => !draft || !item.draft || item.draft === draft;
  return {
    notes: all.filter((item) => item.kind === "note"
      && item.volume === volume && item.section === section && onDraft(item)),
    bookmarks: all.filter((item) => item.kind === "bookmark"
      && item.volume === volume && item.section === section && onDraft(item)),
    sectionChecklist: all.filter((item) => item.kind === "checklist"
      && item.scope === "section" && item.volume === volume && item.section === section),
    bookChecklist: all.filter((item) => item.kind === "checklist" && item.scope === "book"),
  };
}

export function bookmarkAt(items, volume, section, block, draft = null) {
  return (items || []).find((item) => item.kind === "bookmark"
    && item.volume === volume && item.section === section && item.block === block
    && (!draft || !item.draft || item.draft === draft)) || null;
}

export function bookmarks(items) {
  return (items || []).filter((item) => item.kind === "bookmark");
}

export function replaceItem(items, saved) {
  const all = [...(items || [])];
  const at = all.findIndex((item) => item.id === saved.id);
  if (at < 0) all.push(saved);
  else all[at] = { ...all[at], ...saved };
  return all;
}

export function removeItem(items, id) {
  return (items || []).filter((item) => item.id !== id);
}
