// Block ids and quoted phrases <-> ProseMirror positions.
//
// Pure functions of a document node: no view, no DOM, so they are tested by
// building documents from the schema. Positions are ProseMirror's own (one per
// UTF-16 unit of text, one per leaf, one at each node boundary).

import type { Node as PmNode } from "@tiptap/pm/model";
import { locateAll, locateQuote, type Span } from "../doc/locate";

export interface FoundBlock {
  node: PmNode;
  /** Position just before the block. */
  pos: number;
  index: number;
}

export interface Range {
  from: number;
  to: number;
}

export function findBlock(doc: PmNode, id: string): FoundBlock | null {
  let found: FoundBlock | null = null;
  doc.forEach((node, pos, index) => {
    if (!found && node.attrs.id === id) found = { node, pos, index };
  });
  return found;
}

/** The top-level block holding `pos`. */
export function blockAt(doc: PmNode, pos: number): FoundBlock | null {
  if (!doc.childCount) return null;
  const clamped = Math.max(0, Math.min(pos, doc.content.size));
  const index = Math.min(doc.resolve(clamped).index(0), doc.childCount - 1);
  const node = doc.maybeChild(index);
  if (!node) return null;
  let start = 0;
  for (let i = 0; i < index; i += 1) start += (doc.child(i) as PmNode).nodeSize;
  return { node, pos: start, index };
}

export interface TextMap {
  text: string;
  /** The document position of each character of `text`. */
  at: number[];
  /** Where the block's own text ends, for a caret past its last character. */
  end: number;
}

function appendTextblock(node: PmNode, start: number, map: TextMap) {
  node.forEach((child, offset) => {
    if (!child.isText) return;
    const from = start + 1 + offset;
    const text = child.text ?? "";
    for (let i = 0; i < text.length; i += 1) map.at.push(from + i);
    map.text += text;
  });
  map.end = start + node.nodeSize - 1;
}

/** A block's text as the server computes it, and where each character lives. */
export function textMap(block: PmNode, pos: number): TextMap {
  const map: TextMap = { text: "", at: [], end: pos + 1 };
  if (block.isTextblock) {
    appendTextblock(block, pos, map);
    return map;
  }
  block.forEach((item, offset, index) => {
    if (index > 0) {
      map.text += " ";
      map.at.push(map.end);
    }
    appendTextblock(item, pos + 1 + offset, map);
  });
  return map;
}

/** Every place `quote` sits in the block `blockId` now. */
export function quoteRanges(doc: PmNode, blockId: string, quote: string): Range[] {
  const block = findBlock(doc, blockId);
  if (!block || !quote) return [];
  const map = textMap(block.node, block.pos);
  return locateAll(map.text, quote).map((span) => ({
    from: map.at[span.start] as number,
    to: (map.at[span.end - 1] as number) + 1,
  }));
}

/** Which of `map`'s characters `range` covers, when they still read as `quote`. */
export function spanAt(map: TextMap, quote: string, range: Range): Span | null {
  const start = map.at.indexOf(range.from);
  const last = map.at.lastIndexOf(range.to - 1);
  if (start < 0 || last < start) return null;
  const words = map.text.slice(start, last + 1);
  const found = locateQuote(words, quote);
  return found && found.start === 0 && found.end === words.length
    ? { start, end: last + 1 }
    : null;
}

/** `range`, if it still holds `quote` in the block `blockId`; null if not. */
export function quoteStillAt(
  doc: PmNode,
  blockId: string,
  quote: string,
  range: Range,
): Range | null {
  const block = findBlock(doc, blockId);
  if (!block) return null;
  return spanAt(textMap(block.node, block.pos), quote, range) ? range : null;
}

/** Where `quote` sits in the block `blockId` now, or null if it is gone. */
export function quoteRange(doc: PmNode, blockId: string, quote: string): Range | null {
  const block = findBlock(doc, blockId);
  if (!block) return null;
  const map = textMap(block.node, block.pos);
  const span = locateQuote(map.text, quote);
  if (!span || span.end <= span.start) return null;
  return { from: map.at[span.start] as number, to: (map.at[span.end - 1] as number) + 1 };
}

export interface Caret {
  block: string;
  offset: number;
}

/** A caret as a block id and a count of visible characters into it. */
export function caretAt(doc: PmNode, pos: number): Caret | null {
  const block = blockAt(doc, pos);
  const id = block?.node.attrs.id;
  if (!block || !id) return null;
  const map = textMap(block.node, block.pos);
  const offset = map.at.findIndex((at) => at >= pos);
  return { block: id, offset: offset < 0 ? map.text.length : offset };
}

/** The position a saved caret names, or null when its block has gone. */
export function caretPos(doc: PmNode, caret: Caret): number | null {
  const block = findBlock(doc, caret.block);
  if (!block) return null;
  const map = textMap(block.node, block.pos);
  const offset = Math.max(0, caret.offset);
  return offset < map.at.length ? (map.at[offset] as number) : map.end;
}
