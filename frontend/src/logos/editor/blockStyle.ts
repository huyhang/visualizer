// Paragraph or heading, for the blocks under the selection -- keeping each
// block's id, which ProseMirror's own `setBlockType` would replace.

import { Extension } from "@tiptap/core";
import type { EditorState } from "@tiptap/pm/state";
import { blockAt } from "./positions";
import { touchedBlocks } from "./lists";

/** "p" for a paragraph, or a heading level. */
export type BlockStyle = "p" | 1 | 2 | 3;

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    logosBlockStyle: {
      setBlockStyle: (style: BlockStyle) => ReturnType;
    };
  }
}

/** The style of the block at the caret; null in a list, which has none. */
export function currentBlockStyle(state: EditorState): BlockStyle | null {
  const block = blockAt(state.doc, state.selection.from)?.node;
  if (!block) return null;
  if (block.type.name === "heading") return block.attrs.level as 1 | 2 | 3;
  return block.type.name === "paragraph" ? "p" : null;
}

export const LogosBlockStyle = Extension.create({
  name: "logosBlockStyle",
  addCommands() {
    return {
      setBlockStyle:
        (style) =>
        ({ state, tr, dispatch }) => {
          const { paragraph, heading } = state.schema.nodes;
          const blocks = touchedBlocks(
            state.doc,
            state.selection.from,
            state.selection.to,
          ).filter((block) => block.node.isTextblock);
          if (!blocks.length || !paragraph || !heading) return false;
          if (dispatch) {
            for (const { node, pos } of blocks) {
              const id = node.attrs.id;
              if (style === "p") tr.setNodeMarkup(pos, paragraph, { id });
              else tr.setNodeMarkup(pos, heading, { id, level: style });
            }
          }
          return true;
        },
    };
  },
  addKeyboardShortcuts() {
    return {
      "Mod-Alt-0": () => this.editor.commands.setBlockStyle("p"),
      "Mod-Alt-1": () => this.editor.commands.setBlockStyle(1),
      "Mod-Alt-2": () => this.editor.commands.setBlockStyle(2),
      "Mod-Alt-3": () => this.editor.commands.setBlockStyle(3),
    };
  },
});
