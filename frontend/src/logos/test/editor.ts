// A real Tiptap editor on a detached element, with the writer's extensions and
// spies where the page would plug in.

import { Editor } from "@tiptap/core";
import { vi } from "vitest";
import { logosToPm, pmToLogos } from "../doc/convert";
import type { LogosDocument } from "../doc/types";
import { writerExtensions } from "../editor/extensions";

export function makeEditor(document: LogosDocument) {
  let n = 0;
  const makeId = () => `new-${(n += 1)}`;
  const bridge = { onActivate: vi.fn(), onPlacement: vi.fn() };
  const keys = { save: vi.fn(), lookUp: vi.fn(() => false) };
  const editor = new Editor({
    element: window.document.createElement("div"),
    extensions: writerExtensions({ makeId, bridge, keys }),
    content: logosToPm(document, makeId),
  });
  const logos = () => pmToLogos(editor.getJSON(), makeId);
  /** Type `text` at the caret the way a keyboard would, through handleTextInput. */
  const type = (text: string) => {
    for (const character of text) {
      const { from, to } = editor.state.selection;
      const handled = editor.view.someProp("handleTextInput", (handler) =>
        handler(editor.view, from, to, character, () =>
          editor.state.tr.insertText(character, from, to),
        ),
      );
      if (!handled) editor.view.dispatch(editor.state.tr.insertText(character, from, to));
    }
  };
  return { editor, bridge, keys, logos, type };
}
