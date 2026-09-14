// Context-aware quote normalization for structured manuscript prose.

const OPENING_CONTEXT = new Set(["(", "[", "{", "\u2014", "\u2013", "\u2018", "\u201c"]);
const ELISIONS = ["'cause", "'em", "'round", "'til", "'tis", "'twas"];

const alphaNumeric = (value) => Boolean(value && /[\p{L}\p{N}]/u.test(value));

function opens(previous, following) {
  return Boolean(following && !/\s/u.test(following))
    && (!previous || /\s/u.test(previous) || OPENING_CONTEXT.has(previous));
}

export function curlText(text, before = "", after = "") {
  if (!text || (!text.includes("'") && !text.includes('"'))) return text;
  const result = [];
  const characters = Array.from(text);
  for (let index = 0; index < characters.length; index += 1) {
    const character = characters[index];
    const previous = result.at(-1) || Array.from(before).at(-1) || "";
    const following = characters[index + 1] || Array.from(after)[0] || "";
    if (character === '"') {
      result.push(opens(previous, following) ? "\u201c" : "\u201d");
    } else if (character === "'") {
      const tail = characters.slice(index).join("").toLocaleLowerCase();
      const elision = ELISIONS.some((word) => tail.startsWith(word))
        || (/\d/u.test(following) && (!previous || /\s/u.test(previous)));
      result.push(alphaNumeric(previous) && alphaNumeric(following)
        ? "\u2019" : elision ? "\u2019" : opens(previous, following) ? "\u2018" : "\u2019");
    } else {
      result.push(character);
    }
  }
  return result.join("");
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
