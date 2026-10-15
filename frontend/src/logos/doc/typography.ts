// Context-aware quote normalization for manuscript prose.
//
// Two rules, because there are two moments. `curlText` looks both ways and is
// the one for prose that already exists -- a save, a paste; it mirrors
// `logos/typography.py` character for character. `curlTypedMark` looks only
// backwards, because at a caret there is nothing ahead of the mark yet.
// `fixElisions` is what lets the cheap rule catch up with the careful one: a
// leading apostrophe is indistinguishable from an opening single quote until
// its word arrives, so both rules guess the quote and this corrects it.

import { isList, type Inline, type LogosDocument } from "./types";

const OPENING_CONTEXT = new Set(["(", "[", "{", "—", "–", "‘", "“"]);

// Words that begin with an elided letter, and decades written '90s. Anchored on
// the curl rather than the straight mark so it can correct an earlier guess.
const LEADING_ELISION = /‘(?=(?:cause|em|n|round|til|tis|twas)\b|\d\ds\b)/giu;

const alphaNumeric = (value: string) => Boolean(value && /[\p{L}\p{N}]/u.test(value));
const lastChar = (text: string) => Array.from(text).at(-1) ?? "";
const firstChar = (text: string) => Array.from(text)[0] ?? "";

function opens(previous: string, following: string): boolean {
  return (
    Boolean(following && !/\s/u.test(following)) &&
    (!previous || /\s/u.test(previous) || OPENING_CONTEXT.has(previous))
  );
}

/** Re-curl a leading apostrophe that was guessed as an opening quote. */
export function fixElisions(text: string): string {
  return text.includes("‘") ? text.replace(LEADING_ELISION, "’") : text;
}

/** The mark just typed, decided from the text behind the caret alone. */
export function curlTypedMark(before: string, mark: '"' | "'"): string {
  const previous = lastChar(before);
  const opening = !previous || /\s/u.test(previous) || OPENING_CONTEXT.has(previous);
  if (mark === '"') return opening ? "“" : "”";
  return opening ? "‘" : "’";
}

function convert(text: string, before: string, after: string): string {
  const result: string[] = [];
  const characters = Array.from(text);
  characters.forEach((character, index) => {
    const previous = result.at(-1) || lastChar(before);
    const following = characters[index + 1] || firstChar(after);
    if (character === '"') {
      result.push(opens(previous, following) ? "“" : "”");
    } else if (character === "'") {
      result.push(
        alphaNumeric(previous) && alphaNumeric(following)
          ? "’"
          : opens(previous, following)
            ? "‘"
            : "’",
      );
    } else {
      result.push(character);
    }
  });
  return result.join("");
}

/** Curl every straight mark in `text`, given what comes either side of it. */
export function curlText(text: string, before = "", after = ""): string {
  if (!text) return text;
  const straight = text.includes("'") || text.includes('"');
  return fixElisions(straight ? convert(text, before, after) : text);
}

const isCode = (node: Inline) =>
  node.type === "text" && (node.marks ?? []).some((mark) => mark.type === "code");

function nearestText(nodes: Inline[], index: number, direction: 1 | -1): string {
  for (let at = index + direction; at >= 0 && at < nodes.length; at += direction) {
    const node = nodes[at];
    const text = node && "text" in node ? node.text : "";
    if (text) return direction < 0 ? lastChar(text) : firstChar(text);
  }
  return "";
}

function curlRun(nodes: Inline[]): Inline[] {
  const textual = nodes.filter((node) => "text" in node);
  return nodes.map((node) => {
    if (!("text" in node) || isCode(node)) return node;
    const index = textual.indexOf(node);
    return {
      ...node,
      text: curlText(
        node.text,
        nearestText(textual, index, -1),
        nearestText(textual, index, 1),
      ),
    };
  });
}

/** The document with every straight mark curled, code left as written. */
export function curlDocument(document: LogosDocument): LogosDocument {
  return {
    ...document,
    content: document.content.map((block) =>
      isList(block)
        ? {
            ...block,
            content: block.content.map((item) => ({
              ...item,
              content: curlRun(item.content),
            })),
          }
        : { ...block, content: curlRun(block.content) },
    ),
  };
}
