// The editor's whole state as one undoable value: the draft thread, and the
// alternative order being tried beside it, if any. Undo steps back through
// both, so trying an alternative and keeping it is as reversible as a drag.
//
// Typing is the one thing that is not a step per change: a title typed letter
// by letter would take as many undos to take back. A run of edits to the same
// text field folds into one step; anything else starts a new one.

import { record, startHistory, type History } from "../history";
import { insertAt, move, removeAt } from "./order";
import type { ThreadDraft } from "./draft";

export interface Editing {
  draft: ThreadDraft;
  /** The other order being compared, or null when there is no comparison. */
  alternative: string[] | null;
}

export type TextField = "title" | "id" | "overview";

export interface EditorHistory {
  history: History<Editing>;
  /** The text field the last step typed into, so the next keystroke joins it. */
  typing: TextField | null;
}

export function startEditing(draft: ThreadDraft): EditorHistory {
  return { history: startHistory({ draft, alternative: null }), typing: null };
}

const same = (a: Editing, b: Editing) => JSON.stringify(a) === JSON.stringify(b);

/** Apply `next`: a new step, or -- for more typing in the same field -- the same step, revised. */
export function applyEdit(
  state: EditorHistory,
  next: Editing,
  field: TextField | null = null,
): EditorHistory {
  if (field !== null && field === state.typing) {
    return { history: { ...state.history, present: next, future: [] }, typing: field };
  }
  return { history: record(state.history, next, same), typing: field };
}

/** Which order an edit is aimed at: the draft's own (A) or the alternative (B). */
export type Side = "A" | "B";

export function orderOf(editing: Editing, side: Side): string[] {
  return side === "B" ? (editing.alternative ?? []) : editing.draft.events;
}

export function withOrder(editing: Editing, side: Side, order: string[]): Editing {
  return side === "B"
    ? { ...editing, alternative: order }
    : { ...editing, draft: { ...editing.draft, events: order } };
}

export const moveScene = (e: Editing, side: Side, from: number, to: number) =>
  withOrder(e, side, move(orderOf(e, side), from, to));

export const removeScene = (e: Editing, side: Side, index: number) =>
  withOrder(e, side, removeAt(orderOf(e, side), index));

export const addScene = (e: Editing, side: Side, scene: string, at?: number) =>
  withOrder(e, side, insertAt(orderOf(e, side), scene, at));

/** Start comparing: the alternative begins as a copy of the current order. */
export const startComparing = (e: Editing): Editing => ({
  ...e,
  alternative: [...e.draft.events],
});

/** Choose which order goes forward; the comparison ends either way. */
export function keep(e: Editing, side: Side): Editing {
  const events = side === "B" && e.alternative ? e.alternative : e.draft.events;
  return { draft: { ...e.draft, events }, alternative: null };
}
