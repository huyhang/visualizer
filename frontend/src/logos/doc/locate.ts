// Finding a quoted phrase in a block's text again.
//
// A review quotes the prose verbatim, so an exact match is the rule. Two things
// loosen it, and only after an exact match fails: the Writing Coach shortens
// long excerpts with "…" and collapses their whitespace, and a model may have
// echoed a quote with straight marks where the prose has curly ones.

export interface Span {
  start: number;
  end: number;
}

const FOLD: Record<string, string> = { "“": '"', "”": '"', "‘": "'", "’": "'" };

/** `text` folded for comparison, with each folded character's index in the original. */
function folded(text: string): { value: string; at: number[] } {
  let value = "";
  const at: number[] = [];
  let space = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index] as string;
    if (/\s/.test(character)) {
      if (!space) {
        value += " ";
        at.push(index);
      }
      space = true;
      continue;
    }
    space = false;
    value += FOLD[character] ?? character;
    at.push(index);
  }
  return { value, at };
}

const trimEllipsis = (quote: string) =>
  quote
    .replace(/(?:…|\.\.\.)\s*$/u, "")
    .replace(/^\s*(?:…|\.\.\.)/u, "")
    .trim();

/** Where `quote` is in `text`, or null if it is not there any more. */
export function locateQuote(text: string, quote: string): Span | null {
  if (!quote) return null;
  const exact = text.indexOf(quote);
  if (exact >= 0) return { start: exact, end: exact + quote.length };
  const wanted = folded(trimEllipsis(quote)).value.trim();
  if (!wanted) return null;
  const haystack = folded(text);
  const found = haystack.value.indexOf(wanted);
  if (found < 0) return null;
  const last = haystack.at[found + wanted.length - 1] as number;
  return { start: haystack.at[found] as number, end: last + 1 };
}
