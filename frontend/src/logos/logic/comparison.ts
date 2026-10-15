// Draft alignment and prose statistics: which paragraphs two drafts share (by
// stable block id), which changed, and how each reads in numbers.

import { isList, type Block, type Inline, type LogosDocument } from "../doc/types";

const joined = (content: Inline[]) =>
  content
    .map((node) => ("text" in node ? node.text : node.type === "hard_break" ? "\n" : ""))
    .join("");

/** A block's prose; list items are separate lines. */
function blockProse(block: Block): string {
  return isList(block)
    ? block.content.map((item) => joined(item.content)).join("\n")
    : joined(block.content);
}

export interface DraftStats {
  words: number;
  paragraphs: number;
  sentences: number;
  averageSentenceWords: number;
}

export function draftStats(document: LogosDocument): DraftStats {
  const blocks = document.content;
  const text = blocks.map(blockProse).join(" ").trim();
  const words = text ? text.split(/\s+/).length : 0;
  const sentences = (text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) ?? [])
    .map((s) => s.trim())
    .filter(Boolean);
  return {
    words,
    paragraphs: blocks.filter((block) => block.type === "paragraph").length,
    sentences: sentences.length,
    averageSentenceWords: sentences.length ? Math.round(words / sentences.length) : 0,
  };
}

export type RowStatus = "same" | "changed" | "added" | "removed";

export interface ComparedRow {
  id: string;
  status: RowStatus;
  left: string;
  right: string;
}

const row = (left: Block | null, right: Block | null, status: RowStatus): ComparedRow => ({
  id: (left ?? right)!.id,
  status,
  left: left ? blockProse(left) : "",
  right: right ? blockProse(right) : "",
});

export function compareDocuments(left: LogosDocument, right: LogosDocument) {
  const leftBlocks = left.content;
  const leftById = new Map(leftBlocks.map((block) => [block.id, block]));
  const rightIds = new Set(right.content.map((block) => block.id));
  const rows: ComparedRow[] = [];
  let cursor = 0;
  const dropUntil = (end: number) => {
    while (cursor < end) {
      const removed = leftBlocks[cursor++] as Block;
      if (!rightIds.has(removed.id)) rows.push(row(removed, null, "removed"));
    }
  };
  for (const rightBlock of right.content) {
    const matching = leftById.get(rightBlock.id);
    if (!matching) {
      rows.push(row(null, rightBlock, "added"));
      continue;
    }
    dropUntil(leftBlocks.indexOf(matching));
    cursor = leftBlocks.indexOf(matching) + 1;
    rows.push(
      row(
        matching,
        rightBlock,
        blockProse(matching) === blockProse(rightBlock) ? "same" : "changed",
      ),
    );
  }
  dropUntil(leftBlocks.length);
  return { rows, left: draftStats(left), right: draftStats(right) };
}
