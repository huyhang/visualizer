// The reader's display settings -- typeface, line spacing, measure, alignment --
// applied to the writing page too, so prose looks the same written as read.
// Same key and same rules as the reader's `static/js/preferences.js`.

import type { KeyValueStore } from "./preferences";

export const READER_SETTINGS_KEY = "logos-reader-preferences";

const CHOICES = {
  typeface: ["serif", "sans"],
  leading: ["normal", "relaxed"],
  measure: ["medium", "narrow", "wide"],
  align: ["left", "justify"],
} as const;

export type ReadingSettings = { [K in keyof typeof CHOICES]: (typeof CHOICES)[K][number] };

export function readingSettings(store: KeyValueStore): ReadingSettings {
  let given: Record<string, unknown> = {};
  try {
    const parsed = JSON.parse(store.getItem(READER_SETTINGS_KEY) ?? "{}");
    if (parsed && typeof parsed === "object") given = parsed;
  } catch {
    // An unreadable entry means the defaults, as in the reader.
  }
  const pick = <K extends keyof typeof CHOICES>(field: K) => {
    const allowed: readonly string[] = CHOICES[field];
    return (
      allowed.includes(given[field] as string) ? given[field] : allowed[0]
    ) as ReadingSettings[K];
  };
  return {
    typeface: pick("typeface"),
    leading: pick("leading"),
    measure: pick("measure"),
    align: pick("align"),
  };
}

/** Set the settings as `data-` attributes, which `reader.css` turns into prose tokens. */
export function applyReadingSettings(element: HTMLElement, settings: ReadingSettings) {
  for (const [field, value] of Object.entries(settings)) element.dataset[field] = value;
}
