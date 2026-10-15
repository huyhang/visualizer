// Lists the way Logos stores them: a list block of items that hold words
// directly, never nested and never holding paragraphs. ProseMirror's stock list
// commands wrap paragraphs inside items, which this schema rightly refuses, so
// these are the three list edits a writer makes, written for it:
//
//   toggle   the touched blocks become one list, or a list becomes paragraphs
//   Enter    on an empty item leaves the list
//   Backspace at the start of an item takes its bullet off
//
// The first block keeps its id through a toggle, so an anchor on it survives.

import { Extension } from "@tiptap/core";
import type { Node as PmNode, Schema } from "@tiptap/pm/model";
import { TextSelection, type EditorState, type Transaction } from "@tiptap/pm/state";
import type { FoundBlock } from "./positions";

export type ListType = "bullet_list" | "ordered_list";

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    logosLists: {
      toggleLogosList: (type: ListType) => ReturnType;
    };
  }
}

/** The top-level blocks a selection from `from` to `to` touches. */
export function touchedBlocks(doc: PmNode, from: number, to: number): FoundBlock[] {
  const found: FoundBlock[] = [];
  doc.forEach((node, pos, index) => {
    const end = pos + node.nodeSize;
    const touches = from === to ? pos < from && from < end : pos < to && end > from;
    if (touches) found.push({ node, pos, index });
  });
  return found;
}

const items = (node: PmNode): PmNode[] => {
  const children: PmNode[] = [];
  node.forEach((child) => children.push(child));
  return children;
};

/** The blocks that replace `blocks` when they are toggled to or from `type`. */
export function toggledBlocks(
  schema: Schema,
  blocks: FoundBlock[],
  type: ListType,
): PmNode[] {
  const paragraph = schema.nodes.paragraph!;
  const unwrapping = blocks.every((block) => block.node.type.name === type);
  if (unwrapping) {
    return blocks.flatMap((block) =>
      items(block.node).map((item, i) =>
        paragraph.create({ id: i === 0 ? block.node.attrs.id : null }, item.content),
      ),
    );
  }
  const listItem = schema.nodes.list_item!;
  const gathered = blocks.flatMap((block) =>
    block.node.isTextblock
      ? [listItem.create(null, block.node.content)]
      : items(block.node),
  );
  return [schema.nodes[type]!.create({ id: blocks[0]?.node.attrs.id ?? null }, gathered)];
}

function toggle(state: EditorState, tr: Transaction, type: ListType): boolean {
  const { from, to } = state.selection;
  const blocks = touchedBlocks(state.doc, from, to);
  const first = blocks[0];
  const last = blocks.at(-1);
  if (!first || !last) return false;
  const unwrapping = blocks.every((block) => block.node.type.name === type);
  tr.replaceWith(
    first.pos,
    last.pos + last.node.nodeSize,
    toggledBlocks(state.schema, blocks, type),
  );
  // A list adds one level of nesting around the words, so they move by one.
  const shift = unwrapping ? -1 : 1;
  const clamp = (pos: number) =>
    Math.max(1, Math.min(pos + shift, tr.doc.content.size - 1));
  tr.setSelection(
    TextSelection.between(tr.doc.resolve(clamp(from)), tr.doc.resolve(clamp(to))),
  );
  return true;
}

/** Take the item at the caret out of its list as a paragraph, splitting the list around it. */
function liftItem(state: EditorState, keepWords: boolean): Transaction | null {
  const { $from, empty } = state.selection;
  if (!empty || $from.depth !== 2 || $from.parent.type.name !== "list_item") return null;
  if (keepWords ? $from.parentOffset !== 0 : $from.parent.content.size !== 0) return null;
  const list = $from.node(1);
  const listPos = $from.before(1);
  const at = $from.index(1);
  const all = items(list);
  const before = all.slice(0, at);
  const after = all.slice(at + 1);
  const item = all[at] as PmNode;
  const replacement = [
    ...(before.length ? [list.type.create(list.attrs, before)] : []),
    state.schema.nodes.paragraph!.create(
      { id: before.length ? null : list.attrs.id },
      keepWords ? item.content : undefined,
    ),
    ...(after.length ? [list.type.create({ id: null }, after)] : []),
  ];
  const tr = state.tr.replaceWith(listPos, listPos + list.nodeSize, replacement);
  const paragraphPos = listPos + (before.length ? (replacement[0] as PmNode).nodeSize : 0);
  return tr.setSelection(TextSelection.create(tr.doc, paragraphPos + 1));
}

export const LogosLists = Extension.create({
  name: "logosLists",
  addCommands() {
    return {
      toggleLogosList:
        (type) =>
        ({ state, tr, dispatch }) => {
          if (!dispatch)
            return (
              touchedBlocks(state.doc, state.selection.from, state.selection.to).length > 0
            );
          return toggle(state, tr, type);
        },
    };
  },
  addKeyboardShortcuts() {
    const lift = (keepWords: boolean) => () => {
      const tr = liftItem(this.editor.state, keepWords);
      if (!tr) return false;
      this.editor.view.dispatch(tr);
      return true;
    };
    return {
      Enter: lift(false),
      Backspace: lift(true),
      "Mod-Shift-8": () => this.editor.commands.toggleLogosList("bullet_list"),
      "Mod-Shift-7": () => this.editor.commands.toggleLogosList("ordered_list"),
    };
  },
});
