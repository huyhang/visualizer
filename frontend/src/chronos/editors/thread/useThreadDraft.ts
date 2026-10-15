// The editor's draft, with undo and redo. Every change goes through `edit`,
// so nothing the writer does to a thread in this dialog is one-way until Save.

import { useCallback, useEffect, useState } from "react";
import { canRedo, canUndo, redo, undo } from "../../logic/history";
import {
  applyEdit,
  startEditing,
  type Editing,
  type TextField,
} from "../../logic/plotline/editing";
import type { ThreadDraft } from "../../logic/plotline/draft";
import { onTop } from "../../components/common/layers";

export interface ThreadDraftControls {
  editing: Editing;
  /** Make `next` the present; `field` folds a run of typing into one step. */
  edit: (next: Editing, field?: TextField) => void;
  /** Change the present by a function of it, as one step. */
  update: (change: (current: Editing) => Editing) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

export function useThreadDraft(initial: ThreadDraft): ThreadDraftControls {
  const [state, setState] = useState(() => startEditing(initial));
  const edit = useCallback(
    (next: Editing, field?: TextField) =>
      setState((s) => applyEdit(s, next, field ?? null)),
    [],
  );
  const update = useCallback(
    (change: (current: Editing) => Editing) =>
      setState((s) => applyEdit(s, change(s.history.present))),
    [],
  );
  return {
    editing: state.history.present,
    edit,
    update,
    undo: useCallback(
      () => setState((s) => ({ history: undo(s.history), typing: null })),
      [],
    ),
    redo: useCallback(
      () => setState((s) => ({ history: redo(s.history), typing: null })),
      [],
    ),
    canUndo: canUndo(state.history),
    canRedo: canRedo(state.history),
  };
}

/** Whether a key press belongs to a field the writer is typing in, whose own undo should win. */
export function typingIn(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el?.tagName) return false;
  return /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable === true;
}

/** Which history step a key press asks for, if any: ⌘Z undoes, ⇧⌘Z and ⌘Y redo. */
export function historyKey(
  e: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "shiftKey">,
): "undo" | "redo" | null {
  if (!(e.metaKey || e.ctrlKey)) return null;
  const key = e.key.toLowerCase();
  if (key === "z") return e.shiftKey ? "redo" : "undo";
  if (key === "y") return "redo";
  return null;
}

/**
 * Undo and redo from the keyboard while the editor is open and on top: a
 * scene dialog opened from a row takes its own keys.
 */
export function useHistoryKeys(
  onUndo: () => void,
  onRedo: () => void,
  editor: Element | null,
) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const step = historyKey(e);
      if (!step || typingIn(e.target) || !onTop(editor)) return;
      e.preventDefault();
      if (step === "undo") onUndo();
      else onRedo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onUndo, onRedo, editor]);
}
