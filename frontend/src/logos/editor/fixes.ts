// Accepting a suggested fix: the quoted words in one block become the
// replacement, as one undoable edit that autosave and recovery treat exactly
// like typing.
//
// Only the stretch that actually differs is rewritten. A fix seldom changes
// every word it quotes, and the words it keeps may carry what plain text
// cannot -- a linked name, an emphasis -- so "Sir Aldric rode out" becoming
// "Then Sir Aldric rode out" inserts "Then " and leaves the link on the name.
// A fix that rewrites part of a linked name rewrites all of it, unlinked: the
// words no longer name what the link points at.
//
// The fix goes where the words are underlined when the caller says where that
// is -- the same words may come twice in a paragraph -- and a fix given a name
// is remembered, carried along with later edits, so `revertFix` can put back
// exactly what it replaced.

import { Extension } from "@tiptap/core";
import type { Node as PmNode, Slice } from "@tiptap/pm/model";
import { Plugin, PluginKey, TextSelection, type Transaction } from "@tiptap/pm/state";
import { locateQuote, type Span } from "../doc/locate";
import {
  findBlock,
  quoteRange,
  quoteStillAt,
  spanAt,
  textMap,
  type Range,
  type TextMap,
} from "./positions";

export interface Fix {
  blockId: string;
  quote: string;
  replacement: string;
  /** Where the quote is underlined, if it is: the fix is made there. */
  at?: Range | null;
  /** A name to take the fix back by, with `revertFix`. */
  track?: string;
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

const LINKS = new Set(["link", "mention"]);

/** The link or mention on character `offset` of a block's text, if any. */
function linkOn(doc: PmNode, map: TextMap, offset: number) {
  const at = map.at[offset];
  if (at === undefined) return null;
  return doc.nodeAt(at)?.marks.find((mark) => LINKS.has(mark.type.name)) ?? null;
}

/** Text offsets `[first, last)` grown to take in the whole of any linked name
    they cut into; an insertion inside a name takes in all of it. */
export function overLinks(doc: PmNode, map: TextMap, first: number, last: number): Span {
  // Whether a cut before character `i` would split one linked name in two.
  const splits = (i: number) => {
    const left = i > 0 ? linkOn(doc, map, i - 1) : null;
    const right = linkOn(doc, map, i);
    return left !== null && right !== null && left.eq(right);
  };
  let start = first;
  let end = last;
  while (splits(start)) start -= 1;
  while (splits(end)) end += 1;
  return { start, end };
}

/** Where `quote` is in the block: at `at` if it still holds it there, else wherever it is. */
const spanOf = (map: TextMap, quote: string, at?: Range | null): Span | null =>
  (at ? spanAt(map, quote, at) : null) ?? locateQuote(map.text, quote);

interface Tracked {
  /** What the fix put in, and where it is now. */
  from: number;
  to: number;
  inserted: string;
  /** What it took out, marks and links and all. */
  removed: Slice;
}

type FixesMeta = { add: [string, Tracked] } | { drop: string };

const KEEP_TRACKED = 20;

const fixesKey = new PluginKey<Map<string, Tracked>>("logos-fixes");

/** The fixes still remembered, carried along with `tr`. */
function carried(tr: Transaction, held: Map<string, Tracked>): Map<string, Tracked> {
  const meta = tr.getMeta(fixesKey) as FixesMeta | undefined;
  if (!tr.docChanged && !meta) return held;
  const next = new Map<string, Tracked>();
  for (const [name, fix] of held) {
    if (meta && "drop" in meta && meta.drop === name) continue;
    // Words typed at either edge of the fix are not part of it.
    const empty = fix.from === fix.to;
    const from = tr.mapping.map(fix.from, empty ? -1 : 1);
    const to = tr.mapping.map(fix.to, -1);
    next.set(name, { ...fix, from, to });
  }
  if (meta && "add" in meta) {
    next.delete(meta.add[0]);
    next.set(...meta.add);
  }
  while (next.size > KEEP_TRACKED) next.delete(next.keys().next().value as string);
  return next;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    logosFixes: {
      /** Replace `quote` in `blockId` with `replacement`; false if the quote is gone. */
      applyFix: (fix: Fix) => ReturnType;
      /** Put back what the fix named `track` replaced; false if its words have changed since. */
      revertFix: (track: string) => ReturnType;
      /** Select `quote` in `blockId` -- at `at` if it is there -- for the writer to rewrite. */
      selectQuote: (blockId: string, quote: string, at?: Range | null) => ReturnType;
    };
  }
}

export const LogosFixes = Extension.create({
  name: "logosFixes",
  addCommands() {
    return {
      applyFix:
        ({ blockId, quote, replacement, at, track }) =>
        ({ state, tr, dispatch }) => {
          const block = findBlock(state.doc, blockId);
          if (!block || !replacement) return false;
          const map = textMap(block.node, block.pos);
          const span = spanOf(map, quote, at);
          if (!span) return false;
          // Diff against the words as they are, which a loose match may have
          // found with curly quotes where the quote had straight ones.
          const found = map.text.slice(span.start, span.end);
          const edit = minimalEdit(found, replacement);
          const cut = overLinks(
            state.doc,
            map,
            span.start + edit.start,
            span.end - edit.end,
          );
          const insert =
            map.text.slice(cut.start, span.start + edit.start) +
            edit.insert +
            map.text.slice(span.end - edit.end, cut.end);
          // Nothing removed means an insertion, made after the character before it.
          const from =
            cut.end > cut.start ? startOf(map, cut.start) : endOf(map, cut.start);
          const to = cut.end > cut.start ? endOf(map, cut.end) : from;
          if (dispatch) {
            const removed = state.doc.slice(from, to);
            if (insert) {
              tr.insertText(insert, from, to);
              for (const name of LINKS) {
                const type = state.schema.marks[name];
                if (type) tr.removeMark(from, from + insert.length, type);
              }
            } else {
              tr.delete(from, to);
            }
            if (track) {
              const fix = { from, to: from + insert.length, inserted: insert, removed };
              tr.setMeta(fixesKey, { add: [track, fix] } satisfies FixesMeta);
            }
          }
          return true;
        },
      revertFix:
        (track) =>
        ({ state, tr, dispatch }) => {
          const fix = fixesKey.getState(state)?.get(track);
          if (!fix || fix.to < fix.from) return false;
          if (state.doc.textBetween(fix.from, fix.to) !== fix.inserted) return false;
          if (dispatch) {
            tr.replace(fix.from, fix.to, fix.removed);
            tr.setMeta(fixesKey, { drop: track } satisfies FixesMeta);
          }
          return true;
        },
      selectQuote:
        (blockId, quote, at) =>
        ({ state, tr, dispatch }) => {
          const range =
            (at ? quoteStillAt(state.doc, blockId, quote, at) : null) ??
            quoteRange(state.doc, blockId, quote);
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
  addProseMirrorPlugins() {
    return [
      new Plugin<Map<string, Tracked>>({
        key: fixesKey,
        state: { init: () => new Map(), apply: (tr, held) => carried(tr, held) },
      }),
    ];
  },
});
