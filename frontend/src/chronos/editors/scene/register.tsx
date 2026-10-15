// Writing and correcting a scene, from anywhere in a book: the Scenes screen,
// the inspector's "Edit scene", the palette's "New scene". Offered only to a
// reader who may write to the book.

import { useCallback, useState } from "react";
import type { SceneEditOptions } from "../../components/shell/Actions";
import { useOptionalBookScope } from "../../components/shell/BookScope";
import { EMPTY_SLOT, type EditorSlot } from "../slot";
import { SceneEditor } from "./SceneEditor";

/** Which scene is open: null for a new one; undefined when the editor is shut. */
type Open =
  { sceneId: string | null; serial: number; options: SceneEditOptions } | undefined;

export function useSceneEditors(): EditorSlot {
  const scope = useOptionalBookScope();
  const [open, setOpen] = useState<Open>(undefined);
  // The serial remounts the form on every opening, so it never shows a previous draft.
  const newScene = useCallback(
    (options: SceneEditOptions = {}) =>
      setOpen((o) => ({ sceneId: null, serial: (o?.serial ?? 0) + 1, options })),
    [],
  );
  const editScene = useCallback(
    (id: string, options: SceneEditOptions = {}) =>
      setOpen((o) => ({ sceneId: id, serial: (o?.serial ?? 0) + 1, options })),
    [],
  );
  const close = useCallback(() => setOpen(undefined), []);
  if (!scope?.canWrite) return EMPTY_SLOT;
  return {
    actions: { newScene, editScene },
    element: open ? (
      <SceneEditor
        key={open.serial}
        sceneId={open.sceneId}
        onClose={close}
        onSaved={open.options.onSaved}
      />
    ) : null,
  };
}
