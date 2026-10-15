// Every top-level block keeps a unique id, whatever the edit.
//
// Splitting a paragraph copies its attributes, id included; pasting a copy of
// the manuscript brings its ids along; a new heading arrives with none. After
// any transaction that changed the document, a repeated or missing id is
// replaced -- the first holder keeps it, so anything anchored to the passage
// (a review issue, a reader's note) stays with the words it was about.

import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { newBlockId, uniqueIds, type IdFactory } from "../doc/ids";

export const blockIdsKey = new PluginKey("logos-block-ids");

export const BlockIds = Extension.create<{ makeId: IdFactory }>({
  name: "blockIds",
  addOptions: () => ({ makeId: newBlockId }),
  addProseMirrorPlugins() {
    const { makeId } = this.options;
    return [
      new Plugin({
        key: blockIdsKey,
        appendTransaction: (transactions, _old, state) => {
          if (!transactions.some((tr) => tr.docChanged)) return null;
          const held: (string | null)[] = [];
          state.doc.forEach((node) => held.push(node.attrs.id ?? null));
          const wanted = uniqueIds(held, makeId);
          if (wanted.every((id, index) => id === held[index])) return null;
          const tr = state.tr;
          state.doc.forEach((node, pos, index) => {
            if (wanted[index] !== held[index]) {
              tr.setNodeMarkup(pos, undefined, { ...node.attrs, id: wanted[index] });
            }
          });
          // Left in history: an appended transaction joins the edit that caused
          // it, so undoing a split takes its renamed id away with it.
          return tr;
        },
      }),
    ];
  },
});
