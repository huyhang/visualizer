// Pure ordering rules for the editable contents page. DOM events only describe
// what moved and where; these functions produce the complete arrays required by
// Logos' optimistic-concurrency endpoints.

export function availableId(title, known, fallback) {
  const stem = title.toLowerCase().normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || fallback;
  let candidate = stem;
  let suffix = 2;
  while (known.has(candidate)) candidate = `${stem}-${suffix++}`;
  return candidate;
}

export const emptyDocument = () => ({ version: 1, type: "doc", content: [] });

export function allSectionIds(manuscript) {
  return new Set(
    (manuscript.volumes || []).flatMap(
      (volume) => (volume.sections || []).map((section) => section.id),
    ),
  );
}

export function moveBefore(ids, moved, before = null) {
  const current = [...(ids || [])];
  if (!current.includes(moved) || moved === before) return current;
  const reordered = current.filter((id) => id !== moved);
  const at = before === null ? reordered.length : reordered.indexOf(before);
  if (at < 0) return current;
  reordered.splice(at, 0, moved);
  return reordered;
}

export function sameOrder(left, right) {
  return left.length === right.length
    && left.every((value, index) => value === right[index]);
}

export function beforeForPosition(sections, position, moving = null) {
  const ids = (sections || []).map((section) => section.id)
    .filter((id) => id !== moving);
  if (position === "start") return ids[0] || null;
  if (position === "end") return null;
  const after = ids.indexOf(position);
  return after < 0 ? null : (ids[after + 1] || null);
}

export function singletonConflict(section, targetVolume) {
  if (!section || section.kind === "chapter") return null;
  const conflict = (targetVolume.sections || []).find(
    (candidate) => candidate.kind === section.kind && candidate.id !== section.id,
  );
  return conflict || null;
}
