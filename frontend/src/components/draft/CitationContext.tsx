// What a citation chip needs to know about the draft it sits in: its number,
// its source, the quotes taken from it, and how to distrust it. Provided by
// the draft view; a note's preview, which mixes drafts, provides nothing and
// the chips fall back to a plain marker.

import { createContext, useContext } from "react";
import type { SourceRow } from "../../api/types";

export interface CitationInfo {
  number(ref: string): number | null;
  source(ref: string): SourceRow | null;
  quotes(ref: string): string[];
  onDistrust?: (ref: string) => void;
}

const NONE: CitationInfo = { number: () => null, source: () => null, quotes: () => [] };

export const CitationContext = createContext<CitationInfo>(NONE);

export const useCitations = () => useContext(CitationContext);
