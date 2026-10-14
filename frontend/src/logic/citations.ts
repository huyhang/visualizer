// What a draft's citations point at, and how they are numbered for reading.
//
// A draft cites its sources as ordinary wikilinks -- `[[research-inbox/<slug>]]`
// while a source is new, `[[sources/<slug>]]` once accepted -- so a link is a
// citation exactly when it points into one of those two categories.

import type { Fact, SourceRow } from "../api/types";
import type { Inline, Line } from "./wikitext";

export const INBOX = "research-inbox";
export const SOURCES = "sources";

export function isCitation(target: string): boolean {
  return isInboxRef(target) || target.startsWith(`${SOURCES}/`);
}

/** A source still in the inbox: one a steer can tell the box not to read again. */
export function isInboxRef(ref: string): boolean {
  return ref.startsWith(`${INBOX}/`);
}

/** ref -> 1, 2, 3… in the order the draft lists its sources. */
export function sourceNumbers(sources: SourceRow[]): Map<string, number> {
  return new Map(sources.map((row, n) => [row.ref, n + 1]));
}

/** The verbatim quotes the draft's facts take from one source. */
export function quotesFrom(ref: string, facts: Fact[]): string[] {
  const quotes = facts.flatMap((fact) =>
    fact.citations.filter((c) => c.source === ref).map((c) => c.quote),
  );
  return [...new Set(quotes)];
}

/** Every source a run of inline content cites, in order, without repeats. */
export function citedBy(inlines: Inline[]): string[] {
  const refs: string[] = [];
  const walk = (items: Inline[]) => {
    for (const inline of items) {
      if (inline.kind === "link" && isCitation(inline.target)) refs.push(inline.target);
      else if (inline.kind === "bold" || inline.kind === "italic") walk(inline.children);
    }
  };
  walk(inlines);
  return [...new Set(refs)];
}

export function citedByLine(line: Line): string[] {
  return line.kind === "image" ? [] : citedBy(line.inlines);
}

/** A fact as a list item a note can take, carrying its citations with it. */
export function factAsWikitext(fact: Fact): string {
  const refs = [...new Set(fact.citations.map((c) => c.source))];
  return `* ${fact.text.trim()}${refs.map((ref) => ` [[${ref}]]`).join("")}`;
}
