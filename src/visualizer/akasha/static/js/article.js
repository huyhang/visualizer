// The Wikipedia illusion: split a flat document into title / body / infobox and
// reassemble it. `title` and `body` are reserved field names; everything else is
// an infobox fact. This is the only place the mapping lives.

export const TITLE = "title";
export const BODY = "body";

export function splitArticle(document, slug) {
  const doc = document || {};
  const facts = [];
  for (const [key, value] of Object.entries(doc)) {
    if (key === TITLE || key === BODY) continue;
    facts.push({ key, value });
  }
  return {
    title: doc[TITLE] || slug,
    hasTitle: TITLE in doc,
    body: doc[BODY] || "",
    hasBody: BODY in doc,
    facts,
  };
}

// Reassemble a flat document from editor parts. Empty title/body are omitted so
// we never store blank reserved fields.
export function assembleArticle({ title, body, facts }) {
  const doc = {};
  if (title && title.trim()) doc[TITLE] = title.trim();
  if (body && body.length) doc[BODY] = body;
  for (const { key, value } of facts) {
    if (!key || !key.trim()) continue;
    doc[key.trim()] = value;
  }
  return doc;
}

// Parse a fact input string into a scalar or a flat array (comma-separated
// values with more than one element become an array).
export function parseFactValue(raw) {
  const text = String(raw);
  if (text.includes(",")) {
    const parts = text.split(",").map((s) => s.trim()).filter((s) => s.length);
    if (parts.length > 1) return parts.map(coerceScalar);
  }
  return coerceScalar(text.trim());
}

function coerceScalar(s) {
  if (s === "true") return true;
  if (s === "false") return false;
  if (s !== "" && !isNaN(Number(s)) && /^-?\d/.test(s)) return Number(s);
  return s;
}

export function factValueToInput(value) {
  return Array.isArray(value) ? value.join(", ") : String(value);
}
