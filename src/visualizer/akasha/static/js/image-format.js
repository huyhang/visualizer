// Pure serialization shared by the editor and renderer. Image ids are opaque;
// captions are the final field so they may contain separators without escaping.

const ID = "([a-f0-9]{32})";
const IMAGE_RE = new RegExp(`^\\s*\\{\\{image:${ID}\\|(left|center|right|full)\\|(\\d{1,3})\\|(.*?)\\}\\}\\s*$`);
const GALLERY_RE = new RegExp(`^${ID}\\|(.*)$`);

export function parseImageDirective(line) {
  const match = String(line || "").match(IMAGE_RE);
  if (!match) return null;
  const width = Number(match[3]);
  if (width < 10 || width > 100 || (match[2] === "full" && width !== 100)) return null;
  return { media_id: match[1], align: match[2], width, caption: match[4] };
}

export function formatImageDirective({ id, align, width, caption }) {
  const safeAlign = ["left", "center", "right", "full"].includes(align) ? align : "center";
  const safeWidth = safeAlign === "full"
    ? 100
    : Math.max(10, Math.min(100, Number.parseInt(width, 10) || 50));
  const safeCaption = String(caption || "").replaceAll(/\r?\n/g, " ").replaceAll("}}", "} }");
  return `{{image:${id}|${safeAlign}|${safeWidth}|${safeCaption}}}`;
}

export function imageIds(text) {
  const ids = new Set();
  for (const line of String(text || "").split(/\r?\n/)) {
    const placement = parseImageDirective(line);
    if (placement) ids.add(placement.media_id);
  }
  return ids;
}

export function parseGalleryItem(value) {
  const match = String(value || "").match(GALLERY_RE);
  return match ? { media_id: match[1], caption: match[2] } : null;
}

export function isMediaId(value) {
  return typeof value === "string" && new RegExp(`^${ID}$`).test(value);
}

export function formatGalleryItem({ id, caption }) {
  return `${id}|${String(caption || "").replaceAll(/\r?\n/g, " ")}`;
}
