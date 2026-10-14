// The question "Dig deeper" proposes. Akasha has no model of its own, so this
// is assembled from the passage and the topic it came from rather than worded
// by one; the writer edits it before it is sent.
//
// The question is the only writer text the box builds its web searches from,
// and it may be at most 500 characters, so both parts are cut to fit -- the
// passage keeps the larger share, because it is what the writer is asking about.

import { MAX_QUESTION } from "./ask";

const MAX_CONTEXT = 160;
const ELLIPSIS = "…";

export function deepDiveQuestion(passage: string, parentQuestion: string): string {
  const context = clip(parentQuestion.trim(), MAX_CONTEXT);
  const suffix = context ? ` (in the context of: ${context})` : "";
  const room = MAX_QUESTION - suffix.length - "Tell me more about: ".length;
  const subject = clip(passage.trim(), room);
  return `Tell me more about: ${subject}${suffix}`;
}

/** `text` cut to at most `limit` characters, at a word boundary when one is near. */
export function clip(text: string, limit: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= limit) return clean;
  const cut = clean.slice(0, Math.max(0, limit - ELLIPSIS.length));
  // A cut that ends a word keeps it; otherwise back up to the last whole word.
  const endsWord = clean[cut.length] === " ";
  const space = cut.lastIndexOf(" ");
  const head = endsWord || space <= cut.length * 0.6 ? cut : cut.slice(0, space);
  return head.replace(/[\s,;:.]+$/, "") + ELLIPSIS;
}
