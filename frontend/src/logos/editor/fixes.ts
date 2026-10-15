// Accepting a suggested fix: the quoted words in one block become the
// replacement, as one undoable edit that autosave and recovery treat exactly
// like typing.
//
// Only the stretch that actually differs is rewritten. A fix seldom changes
// every word it quotes, and the words it keeps may carry what plain text
// cannot -- a linked name, an emphasis -- so "Sir Aldric rode out" becoming
// "Then Sir Aldric rode out" inserts "Then " and leaves the link on the name.

import { Extension } from "@tiptap/core";
import { TextSelection } from "@tiptap/pm/state";
import { locateQuote } from "../doc/locate";
import { findBlock, quoteRange, textMap, type TextMap } from "./positions";

export interface Fix {
  blockId: string;
  quote: string;
  replacement: string;
}

/** The smallest edit turning `before` into `after`: what to keep at each end. */
export function minimalEdit(before: string, after: string) {
  let start = 0;
  while (start < before.length && start < after.length && before[start] === after[start])
    start += 1;
  let end = 0;
  while (
    end < before.length - start &&
    end < after.length - start &&
    before[before.length - 1 - end] === after[after.length - 1 - end]
  ) {
    end += 1;
  }
  return { start, end, insert: after.slice(start, after.length - end) };
}

/** Where character `offset` of a block's text starts. */
const startOf = (map: TextMap, offset: number): number =>
  offset < map.at.length ? (map.at[offset] as number) : map.end;

/** Just after character `offset - 1`: an exclusive end that never takes in a
    hard break or item boundary lying between two characters. */
const endOf = (map: TextMap, offset: number): number =>
  offset > 0 ? (map.at[offset - 1] as number) + 1 : startOf(map, 0);

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    logosFixes: {
      /** Replace `quote` in `blockId` with `replacement`; false if the quote is gone. */
      applyFix: (fix: Fix) => ReturnType;
      /** Select `quote` in `blockId`, for the writer to rewrite by hand. */
      selectQuote: (blockId: string, quote: string) => ReturnType;
    };
  }
}

export const LogosFixes = Extension.create({
  name: "logosFixes",
  addCommands() {
    return {
      applyFix:
        ({ blockId, quote, replacement }) =>
        ({ state, tr, dispatch }) => {
          const block = findBlock(state.doc, blockId);
          if (!block || !replacement) return false;
          const map = textMap(block.node, block.pos);
          const span = locateQuote(map.text, quote);
          if (!span) return false;
          // Diff against the words as they are, which a loose match may have
          // found with curly quotes where the quote had straight ones.
          const found = map.text.slice(span.start, span.end);
          const edit = minimalEdit(found, replacement);
          const first = span.start + edit.start;
          const last = span.end - edit.end;
          // Nothing removed means an insertion, made after the character before it.
          const from = last > first ? startOf(map, first) : endOf(map, first);
          const to = last > first ? endOf(map, last) : from;
          if (dispatch) {
            if (edit.insert) tr.insertText(edit.insert, from, to);
            else tr.delete(from, to);
          }
          return true;
        },
      selectQuote:
        (blockId, quote) =>
        ({ state, tr, dispatch }) => {
          const range = quoteRange(state.doc, blockId, quote);
          if (!range) return false;
          if (dispatch) {
            tr.setSelection(
              TextSelection.create(tr.doc, range.from, range.to),
            ).scrollIntoView();
          }
          return true;
        },
    };
  },
});
