// Small pieces of wording the workspace shows in more than one place.

export interface Timed {
  scheduled?: boolean | null;
  start_tick?: number | null;
  end_tick?: number | null;
  start_label?: string | null;
  end_label?: string | null;
}

/** "Day 3 → Day 4", "Day 3" for an instant, or "unscheduled". */
export function timeframe(scene: Timed): string {
  if (scene.scheduled === false) return "unscheduled";
  const start = scene.start_label ?? scene.start_tick;
  if (start === null || start === undefined) return "unscheduled";
  if (scene.end_label && scene.end_label !== scene.start_label) {
    return `${start} → ${scene.end_label}`;
  }
  return String(start);
}

/**
 * Akasha wikitext as plain prose: `[[locations/highkeep|Highkeep]]` reads
 * "Highkeep", and `[[characters/aldric]]` reads "aldric".
 */
export function plainBody(body: string | null | undefined): string {
  return String(body ?? "").replace(/\[\[([^\]]+)\]\]/g, (_, inner: string) => {
    const parts = inner.split("|");
    const shown = parts.length > 1 ? (parts[1] ?? "") : (parts[0] ?? "");
    return shown.split("/").pop() ?? shown;
  });
}

/** "1 problem", "3 problems". */
export function plural(count: number, noun: string, many = `${noun}s`): string {
  return `${count} ${count === 1 ? noun : many}`;
}

/**
 * The id a title becomes: the same rule as the classic page's shared
 * `slug.js`, so a scene and the article it references reach the same id from
 * the same title. "" when nothing usable is left, for the caller to refuse.
 */
export function slugify(title: string): string {
  return String(title || "")
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
