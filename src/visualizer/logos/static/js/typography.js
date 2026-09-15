// Context-aware quote normalization for structured manuscript prose.
//
// Two rules, because there are two moments. `curlText` looks both ways and is
// the one for prose that already exists -- a save, a paste, an API write; it
// mirrors `logos/typography.py` character for character. `curlTypedMark` looks
// only backwards, because at a caret there is nothing ahead of the mark yet.
// `fixElisions` is what lets the cheap rule catch up with the careful one: a
// leading apostrophe is indistinguishable from an opening single quote until
// its word arrives, so both rules guess the quote and this corrects it.

const OPENING_CONTEXT = new Set(["(", "[", "{", "—", "–", "‘", "“"]);

// Words that begin with an elided letter, and decades written '90s. Anchored on
// the curl rather than the straight mark so it can correct an earlier guess.
const LEADING_ELISION =
  /‘(?=(?:cause|em|n|round|til|tis|twas)\b|\d\ds\b)/giu;

const alphaNumeric = (value) => Boolean(value && /[\p{L}\p{N}]/u.test(value));

function opens(previous, following) {
  return Boolean(following && !/\s/u.test(following))
    && (!previous || /\s/u.test(previous) || OPENING_CONTEXT.has(previous));
}

/** Re-curl a leading apostrophe that was guessed as an opening quote. */
export function fixElisions(text) {
  return text.includes("‘") ? text.replace(LEADING_ELISION, "’") : text;
}

/** The mark just typed, decided from the text behind the caret alone. */
export function curlTypedMark(before, mark) {
  const previous = Array.from(before).at(-1) || "";
  const opening = !previous || /\s/u.test(previous) || OPENING_CONTEXT.has(previous);
  if (mark === '"') return opening ? "“" : "”";
  return opening ? "‘" : "’";
}

function convert(text, before, after) {
  const result = [];
  const characters = Array.from(text);
  for (let index = 0; index < characters.length; index += 1) {
    const character = characters[index];
    const previous = result.at(-1) || Array.from(before).at(-1) || "";
    const following = characters[index + 1] || Array.from(after)[0] || "";
    if (character === '"') {
      result.push(opens(previous, following) ? "“" : "”");
    } else if (character === "'") {
      result.push(alphaNumeric(previous) && alphaNumeric(following)
        ? "’"
        : opens(previous, following) ? "‘" : "’");
    } else {
      result.push(character);
    }
  }
  return result.join("");
}

export function curlText(text, before = "", after = "") {
  if (!text) return text;
  const straight = text.includes("'") || text.includes('"');
  return fixElisions(straight ? convert(text, before, after) : text);
}

function isCode(node) {
  return (node.marks || []).some((mark) => mark.type === "code");
}

function nearestText(nodes, index, direction) {
  for (let cursor = index + direction; cursor >= 0 && cursor < nodes.length; cursor += direction) {
    const text = nodes[cursor].text || "";
    if (text) {
      const characters = Array.from(text);
      return direction < 0 ? characters.at(-1) : characters[0];
    }
  }
  return "";
}

function curlNodes(nodes) {
  const textual = nodes.filter((node) => typeof node.text === "string");
  textual.forEach((node, index) => {
    if (!isCode(node)) {
      node.text = curlText(
        node.text,
        nearestText(textual, index, -1),
        nearestText(textual, index, 1),
      );
    }
  });
}

export function curlDocument(document) {
  const result = JSON.parse(JSON.stringify(document));
  for (const block of result.content || []) {
    const groups = ["bullet_list", "ordered_list"].includes(block.type)
      ? (block.content || []).map((item) => item.content || [])
      : [block.content || []];
    groups.forEach(curlNodes);
  }
  return result;
}
