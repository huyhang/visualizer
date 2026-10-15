// The editor, assembled: the schema plus the writer's behaviours. Everything
// the editor reports outward arrives as an injected callback, so the same
// extensions run in a test with spies and in the page with the real workspace.

import { Extension, type Extensions } from "@tiptap/core";
import { Placeholder, UndoRedo } from "@tiptap/extensions";
import type { IdFactory } from "../doc/ids";
import { schemaExtensions } from "../doc/schema";
import { Annotations, type AnnotationBridge } from "./annotations";
import { BlockIds } from "./blockIds";
import { LogosBlockStyle } from "./blockStyle";
import { LogosFixes } from "./fixes";
import { LogosLists } from "./lists";
import { LogosMentions } from "./mentions";
import { SmartQuotes } from "./smartQuotes";

export interface WriterKeys {
  /** Cmd/Ctrl+S: save now rather than when typing pauses. */
  save: () => void;
  /** Cmd/Ctrl+K: look the selected words up in Akasha. False if nothing is selected. */
  lookUp: () => boolean;
}

const Keys = Extension.create<{ keys: WriterKeys }>({
  name: "writerKeys",
  addOptions: () => ({ keys: { save: () => {}, lookUp: () => false } }),
  addKeyboardShortcuts() {
    const { keys } = this.options;
    return {
      "Mod-s": () => {
        keys.save();
        return true;
      },
      "Mod-k": () => keys.lookUp(),
    };
  },
});

export interface EditorDeps {
  makeId: IdFactory;
  bridge: AnnotationBridge;
  keys: WriterKeys;
  placeholder?: string;
}

export function writerExtensions({
  makeId,
  bridge,
  keys,
  placeholder,
}: EditorDeps): Extensions {
  return [
    ...schemaExtensions,
    UndoRedo,
    Placeholder.configure({ placeholder: placeholder ?? "Begin writing…" }),
    BlockIds.configure({ makeId }),
    LogosLists,
    LogosBlockStyle,
    LogosMentions,
    LogosFixes,
    SmartQuotes,
    Annotations.configure({ bridge }),
    Keys.configure({ keys }),
  ];
}
