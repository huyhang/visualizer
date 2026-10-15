// Akasha mentions: linking selected words to an article, and taking a link off.
// A mention is a mark, so linking never changes the words and unlinking leaves
// them exactly as they were.

import { Extension, getMarkRange } from "@tiptap/core";
import type { EditorState } from "@tiptap/pm/state";
import type { ArticleRef } from "../doc/types";
import type { Range } from "./positions";

export interface MentionAt extends ArticleRef {
  kind: "mention" | "article_link";
  text: string;
  range: Range;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    logosMentions: {
      linkMention: (range: Range, ref: ArticleRef) => ReturnType;
      unlinkMention: (pos: number) => ReturnType;
    };
  }
}

/** The linked phrase at `pos`, whole, or null. */
export function mentionAt(state: EditorState, pos: number): MentionAt | null {
  const type = state.schema.marks.mention;
  if (!type) return null;
  const $pos = state.doc.resolve(pos);
  const mark =
    $pos.marks().find((m) => m.type === type) ??
    $pos.nodeAfter?.marks.find((m) => m.type === type);
  if (!mark) return null;
  const range = getMarkRange($pos, type, mark.attrs);
  if (!range) return null;
  const { kind, database, collection, id } = mark.attrs;
  return {
    kind: kind === "article_link" ? "article_link" : "mention",
    database,
    collection,
    id,
    text: state.doc.textBetween(range.from, range.to),
    range,
  };
}

/** Whether `range` can be linked: some words, all inside one block. */
export function linkable(state: EditorState, range: Range): boolean {
  if (range.to <= range.from) return false;
  const $from = state.doc.resolve(range.from);
  const $to = state.doc.resolve(range.to);
  return (
    $from.sameParent($to) &&
    $from.parent.isTextblock &&
    Boolean(state.doc.textBetween(range.from, range.to).trim())
  );
}

export const LogosMentions = Extension.create({
  name: "logosMentions",
  addCommands() {
    return {
      linkMention:
        (range, ref) =>
        ({ state, tr, dispatch }) => {
          const type = state.schema.marks.mention;
          if (!type || !linkable(state, range)) return false;
          if (dispatch)
            tr.addMark(range.from, range.to, type.create({ kind: "mention", ...ref }));
          return true;
        },
      unlinkMention:
        (pos) =>
        ({ state, tr, dispatch }) => {
          const found = mentionAt(state, pos);
          const type = state.schema.marks.mention;
          if (!found || !type) return false;
          if (dispatch) tr.removeMark(found.range.from, found.range.to, type);
          return true;
        },
    };
  },
});
