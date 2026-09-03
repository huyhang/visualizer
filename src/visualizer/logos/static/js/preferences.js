// Everything the reader remembers about how you like to read.
//
// One key, one shape, one pair of functions. The reading mode and the four
// display choices live together because they are the same kind of thing -- a
// per-browser view preference the server never sees, needing no route, no
// permission check and no migration -- and because a second module would mean
// a second copy of the storage guard at the bottom of this file.
//
// Deliberately *not* in here: theme and text size. Those are shared across all
// four services and the header already owns them (`prefs.js`). A reader that
// kept its own copy would have two sources of truth for one setting, and a
// "reset" here would silently undo a choice made in Articles.
//
// Storage is injected rather than imported, so this runs under node with a
// plain dictionary and needs no DOM. Every field is read through an allowlist:
// a value this reader does not know -- an older key, a hand-edited entry, a
// newer writer -- falls back to the default instead of reaching the page.

export const STORAGE_KEY = "logos-reader-preferences";

export const FOCUSED = "focused";
export const FULL = "full";

// First entry is the default. Focused leads deliberately: showing nothing from
// another service is the safe answer, so Full View is always something you
// chose rather than something you were given.
//
export const CHOICES = Object.freeze({
  mode: [FOCUSED, FULL],
  typeface: ["serif", "sans"],
  leading: ["normal", "relaxed"],
  measure: ["medium", "narrow", "wide"],
  align: ["left", "justify"],
});

export const DISPLAY_FIELDS = Object.freeze(
  Object.keys(CHOICES).filter((field) => field !== "mode"),
);

export const DEFAULTS = Object.freeze(
  Object.fromEntries(
    Object.entries(CHOICES).map(([field, allowed]) => [field, allowed[0]]),
  ),
);

export function parsePreferences(value) {
  const given = value && typeof value === "object" ? value : {};
  return Object.fromEntries(
    Object.entries(CHOICES).map(([field, allowed]) => [
      field,
      allowed.includes(given[field]) ? given[field] : allowed[0],
    ]),
  );
}

export function showsChronos(preferences) {
  return parsePreferences(preferences).mode === FULL;
}

export function otherMode(mode) {
  return mode === FULL ? FOCUSED : FULL;
}

/** Display back to defaults; the reading mode is not a display choice. */
export function resetDisplay(preferences) {
  const current = parsePreferences(preferences);
  return { ...current, ...Object.fromEntries(DISPLAY_FIELDS.map((f) => [f, DEFAULTS[f]])) };
}

// -- persistence --------------------------------------------------------------
//
// Both guards are the same one: private browsing throws on every touch of
// localStorage, and a reader that cannot remember your typeface should still
// show you the prose.

export function readPreferences(storage) {
  try {
    return parsePreferences(JSON.parse(storage.getItem(STORAGE_KEY)));
  } catch (_error) {
    return { ...DEFAULTS };
  }
}

/** Merge a patch over what is stored, normalise, persist, and return it. */
export function writePreferences(storage, patch) {
  const next = parsePreferences({ ...readPreferences(storage), ...patch });
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch (_error) {
    // Applies to this page; it just will not be remembered for the next one.
  }
  return next;
}
