// The Tiptap editor for one draft. What the editor reports outward -- a change,
// a click on an underline, where annotations landed, Cmd+S, Cmd+K -- goes to
// the callbacks given here, read fresh each time through `useLatest`, so the
// editor is built once and never rebuilt by a re-render.

import { useEditor } from "@tiptap/react";
import { useMemo } from "react";
import { logosToPm } from "../doc/convert";
import type { IdFactory } from "../doc/ids";
import type { LogosDocument } from "../doc/types";
import type { Placement } from "../editor/annotations";
import { writerExtensions } from "../editor/extensions";
import { useLatest } from "./useLatest";

export interface EditorCallbacks {
  onChange: () => void;
  onActivate: (id: string, anchor: HTMLElement) => void;
  onPlacement: (placement: Placement) => void;
  onSave: () => void;
  onLookUp: () => boolean;
}

export function useWriterEditor(
  initial: LogosDocument,
  makeId: IdFactory,
  label: string,
  callbacks: EditorCallbacks,
) {
  const latest = useLatest(callbacks);
  const extensions = useMemo(
    () =>
      writerExtensions({
        makeId,
        bridge: {
          onActivate: (id, anchor) => latest.current.onActivate(id, anchor),
          onPlacement: (placement) => latest.current.onPlacement(placement),
        },
        keys: {
          save: () => latest.current.onSave(),
          lookUp: () => latest.current.onLookUp(),
        },
      }),
    [makeId, latest],
  );
  return useEditor(
    {
      extensions,
      content: logosToPm(initial, makeId),
      immediatelyRender: true,
      shouldRerenderOnTransaction: false,
      editorProps: {
        attributes: {
          class: "prose lw-editor",
          role: "textbox",
          "aria-multiline": "true",
          "aria-label": label,
          spellcheck: "true",
        },
      },
      onUpdate: () => latest.current.onChange(),
    },
    [],
  );
}
