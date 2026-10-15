// How a keyboard shortcut is written on the page: ⌘K on a Mac, Ctrl K anywhere
// else, where there is no ⌘ to press.

const MAC = /Mac|iPhone|iPad/.test(
  typeof navigator === "undefined" ? "" : navigator.platform || navigator.userAgent,
);

/** "⌘K" or "Ctrl K" for the modifier-plus-`key` shortcut, as this machine names it. */
export function shortcutLabel(key: string, mac = MAC): string {
  return mac ? `⌘${key}` : `Ctrl ${key}`;
}
