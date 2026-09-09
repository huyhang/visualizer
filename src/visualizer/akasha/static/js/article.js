// The Wikipedia illusion: split a flat document into its article parts and
// reassemble it. This is the only place the reserved-field mapping lives.

import { formatGalleryItem, parseGalleryItem, parseImageDirective } from "./image-format.js";

export const TITLE = "title";
export const BODY = "body";
export const PROFILE_IMAGE = "profile_image";
export const GALLERY = "gallery";

const RESERVED = new Set([TITLE, BODY, PROFILE_IMAGE, GALLERY]);

export function splitArticle(document, slug) {
  const doc = document || {};
  const facts = [];
  for (const [key, value] of Object.entries(doc)) {
    if (RESERVED.has(key)) continue;
    facts.push({ key, value });
  }
  const gallery = Array.isArray(doc[GALLERY])
    ? doc[GALLERY].map(parseGalleryItem).filter(Boolean)
    : [];
  const attached = new Set(gallery.map((item) => item.media_id));
  for (const line of String(doc[BODY] || "").split(/\r?\n/)) {
    const placement = parseImageDirective(line);
    if (placement && !attached.has(placement.media_id)) {
      gallery.push({ media_id: placement.media_id, caption: placement.caption });
      attached.add(placement.media_id);
    }
  }
  const profileImage = attached.has(doc[PROFILE_IMAGE]) ? doc[PROFILE_IMAGE] : null;
  return {
    title: doc[TITLE] || slug,
    hasTitle: TITLE in doc,
    body: doc[BODY] || "",
    hasBody: BODY in doc,
    facts,
    profileImage,
    gallery,
  };
}

// Reassemble a flat document from editor parts. Empty title/body are omitted so
// we never store blank reserved fields.
export function assembleArticle({ title, body, facts, profileImage = null, gallery = [] }) {
  const doc = {};
  if (title && title.trim()) doc[TITLE] = title.trim();
  if (body && body.length) doc[BODY] = body;
  if (gallery.length) {
    doc[GALLERY] = gallery.map((item) => formatGalleryItem({
      id: item.media_id || item.id,
      caption: item.caption,
    }));
  }
  if (profileImage && gallery.some((item) => (item.media_id || item.id) === profileImage)) {
    doc[PROFILE_IMAGE] = profileImage;
  }
  for (const { key, value } of facts) {
    const cleanKey = key && key.trim();
    if (!cleanKey || RESERVED.has(cleanKey)) continue;
    doc[cleanKey] = value;
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
