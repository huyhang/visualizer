// Rearranging a thread's own scenes: the list operations the editor's drag,
// keyboard and buttons all come down to. Pure, so every way of moving a scene
// moves it the same way.

/** `list` with the item at `from` taken out and put back at `to`. */
export function move<T>(list: readonly T[], from: number, to: number): T[] {
  if (from === to || from < 0 || from >= list.length || to < 0 || to >= list.length)
    return [...list];
  const out = [...list];
  const [item] = out.splice(from, 1);
  out.splice(to, 0, item as T);
  return out;
}

/**
 * Where a dragged row lands when dropped on row `index`: before it, or after it
 * when dropped below its midpoint. Taking the dragged row out first shifts
 * every later position up by one, which is what the last line accounts for.
 */
export function dropIndex(from: number, index: number, below: boolean): number {
  let to = below ? index + 1 : index;
  if (from < to) to -= 1;
  return to;
}

export function insertAt<T>(list: readonly T[], item: T, at: number = list.length): T[] {
  const out = [...list];
  out.splice(Math.max(0, Math.min(at, out.length)), 0, item);
  return out;
}

export function removeAt<T>(list: readonly T[], index: number): T[] {
  return list.filter((_, n) => n !== index);
}

export interface Timing {
  scheduled?: boolean | null;
  start_tick?: number | null;
}

/**
 * Dated scenes by start, undated ones after them in the order they were in:
 * the one-click fix for a thread whose scenes were simply typed out of order.
 */
export function byTime(
  ids: readonly string[],
  timingOf: (id: string) => Timing | undefined,
): string[] {
  const dated = (id: string) => {
    const t = timingOf(id);
    return Boolean(t?.scheduled && t.start_tick !== null && t.start_tick !== undefined);
  };
  const start = (id: string) => timingOf(id)?.start_tick ?? 0;
  const scheduled = ids.filter(dated).sort((a, b) => start(a) - start(b));
  return [...scheduled, ...ids.filter((id) => !dated(id))];
}

/** The keyboard's move for a focused row, or null when the key is not one. */
export function keyMove(key: string, index: number, length: number): number | null {
  const to = key === "ArrowUp" ? index - 1 : key === "ArrowDown" ? index + 1 : null;
  if (to === null || to < 0 || to >= length) return null;
  return to;
}
