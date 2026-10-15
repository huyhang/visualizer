// Undo and redo over any value: a draft thread's order, a form. Immutable, so
// a step is a new history and React sees it change.

export interface History<T> {
  past: T[];
  present: T;
  future: T[];
}

export function startHistory<T>(present: T): History<T> {
  return { past: [], present, future: [] };
}

/** Record `next` as the new present. Doing something new forgets what was undone. */
export function record<T>(
  history: History<T>,
  next: T,
  same: (a: T, b: T) => boolean = Object.is,
): History<T> {
  if (same(history.present, next)) return history;
  return { past: [...history.past, history.present], present: next, future: [] };
}

export function undo<T>(history: History<T>): History<T> {
  const previous = history.past[history.past.length - 1];
  if (previous === undefined) return history;
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future],
  };
}

export function redo<T>(history: History<T>): History<T> {
  const [next, ...rest] = history.future;
  if (next === undefined) return history;
  return { past: [...history.past, history.present], present: next, future: rest };
}

export const canUndo = <T>(history: History<T>) => history.past.length > 0;
export const canRedo = <T>(history: History<T>) => history.future.length > 0;

/** Two lists the same, item for item: the usual `same` for an order. */
export function sameList<T>(a: readonly T[], b: readonly T[]): boolean {
  return a.length === b.length && a.every((x, n) => Object.is(x, b[n]));
}
