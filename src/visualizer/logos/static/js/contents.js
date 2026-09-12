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

export function beforeForPosition(sections, position) {
  const ids = (sections || []).map((section) => section.id);
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

// The kinds a volume can hold, and which of them it can still take. A volume
// holds any number of chapters but at most one prologue, epilogue and glossary.
//
// Every kind is always returned. Dropping the unavailable ones from the menu
// was the first thing tried and it reads as a broken feature: a writer looking
// for "Prologue" finds it simply missing, with nothing to say whether the
// option is gone or the app is. Offering it disabled, with the reason, teaches
// the rule instead.
export const SECTION_KINDS = ["chapter", "prologue", "epilogue", "glossary"];
const SINGLETON_KINDS = new Set(["prologue", "epilogue", "glossary"]);

export function sectionKindChoices(volume) {
  const taken = new Set((volume?.sections || []).map((section) => section.kind));
  return SECTION_KINDS.map((kind) => ({
    kind,
    available: !SINGLETON_KINDS.has(kind) || !taken.has(kind),
  }));
}

export const availableKinds = (volume) => sectionKindChoices(volume)
  .filter((choice) => choice.available)
  .map((choice) => choice.kind);

// -- where a dragged thing would land ---------------------------------------
//
// Touch dragging has to hit-test by hand: once a pointer is captured, every
// event goes to the handle rather than to whatever is under the finger. These
// take the rendered geometry -- volumes as zones, their rows as slots -- and a
// pointer position, and answer in the vocabulary the move API already speaks:
// a destination volume and the section to insert in front of, null to append.

function nearestZone(zones, y) {
  let best = null;
  let gap = Infinity;
  for (const zone of zones) {
    const distance = y < zone.top ? zone.top - y : y - zone.bottom;
    if (distance < gap) {
      gap = distance;
      best = zone;
    }
  }
  return best;
}

export function dropAt(zones, y) {
  const list = zones || [];
  if (!list.length) return null;
  const zone = list.find((candidate) => y >= candidate.top && y <= candidate.bottom)
    || nearestZone(list, y);
  if (!zone) return null;
  // An empty volume is a legitimate destination, and the only place a first
  // chapter can go.
  for (const row of zone.sections || []) {
    if (y < (row.top + row.bottom) / 2) return { volume: zone.volume, before: row.id };
  }
  return { volume: zone.volume, before: null };
}

export function volumeDropAt(zones, y, dragged) {
  const list = (zones || []).filter((zone) => zone.volume !== dragged);
  if (!list.length) return null;
  for (const zone of list) {
    if (y < (zone.top + zone.bottom) / 2) return { before: zone.volume };
  }
  return { before: null };
}

// Whether a failed move is worth retrying, and what to tell the writer.
//
// A conflict or a server/network failure may have landed halfway -- the move is
// idempotent, so repeating it against a fresh outline finishes it. A refusal (a
// name already taken, a second prologue, an anchor that has gone) fails the same
// way however often it is tried, so a Retry button would only mislead.
export function moveFailure(error) {
  if (!error || error.network) {
    return { retriable: true, detail: "the request could not reach the server" };
  }
  if (error.code === "REVISION_CONFLICT") {
    return { retriable: true, detail: "someone else changed the outline" };
  }
  if (error.status >= 500 || error.status === 429) {
    return { retriable: true, detail: "the server had a problem" };
  }
  return { retriable: false, detail: null };
}
