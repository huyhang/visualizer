// The Wikipedia illusion: split a flat document into its article parts and
// reassemble it. This is the only place the reserved-field mapping lives.

import {
  formatGalleryItem, isMediaId, parseGalleryItem, parseImageDirective,
} from "./image-format.js";

export const TITLE = "title";
export const BODY = "body";
export const PROFILE_IMAGE = "profile_image";
export const GALLERY = "gallery";

// `title` and `body` are ours unconditionally. The two image fields are ours
// only when they hold image references: an article that has always listed its
// wings under `gallery` keeps that list as an ordinary infobox fact, rather
// than having it hidden by a feature it predates.
export function galleryEntries(value) {
  if (!Array.isArray(value) || !value.length) return null;
  const parsed = value.map(parseGalleryItem);
  return parsed.every(Boolean) ? parsed : null;
}

export function splitArticle(document, slug) {
  const doc = document || {};
  const stored = galleryEntries(doc[GALLERY]);
  const claimsProfile = isMediaId(doc[PROFILE_IMAGE]);
  const facts = [];
  for (const [key, value] of Object.entries(doc)) {
    if (key === TITLE || key === BODY) continue;
    if (key === GALLERY && stored) continue;
    if (key === PROFILE_IMAGE && claimsProfile) continue;
    facts.push({ key, value });
  }
  const gallery = stored ? [...stored] : [];
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
  for (const { key, value } of facts) {
    const cleanKey = key && key.trim();
    if (!cleanKey || cleanKey === TITLE || cleanKey === BODY) continue;
    doc[cleanKey] = value;
  }
  // Written last, and only when there is something to write: an article with
  // no attachments leaves both names to whatever fact was already using them.
  if (gallery.length) {
    doc[GALLERY] = gallery.map((item) => formatGalleryItem({
      id: item.media_id || item.id,
      caption: item.caption,
    }));
    if (profileImage && gallery.some((item) => (item.media_id || item.id) === profileImage)) {
      doc[PROFILE_IMAGE] = profileImage;
    }
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
