// What a reader sees of a block, as `logos/richtext.py` computes it. Review
// quotes are copied out of exactly this text, so the editor must agree with it
// to find them again: mentions and links are words, a hard break is nothing,
// and list items are joined by one space.

import { isList, type Block, type Inline, type LogosDocument } from "./types";

const inlineText = (nodes: Inline[]) =>
  nodes.map((node) => ("text" in node ? node.text : "")).join("");

export function blockText(block: Block): string {
  return isList(block)
    ? block.content.map((item) => inlineText(item.content)).join(" ")
    : inlineText(block.content);
}

/** Words as the server counts them: every visible run split on whitespace. */
export function wordCount(document: LogosDocument): number {
  let words = 0;
  for (const block of document.content) {
    const runs = isList(block)
      ? block.content.flatMap((item) => item.content)
      : block.content;
    for (const node of runs) {
      if ("text" in node) words += node.text.split(/\s+/).filter(Boolean).length;
    }
  }
  return words;
}
