// Akasha's wikitext subset, parsed into a tree React can render -- the same
// language as akasha/static/js/wikitext.js, but producing data rather than an
// HTML string, so nothing written by a model ever reaches innerHTML.
//
//   '''bold'''  ''italic''  == heading ==  * list item  [[target]] / [[target|label]]
//   {{image:<id>|<align>|<width>|<caption>}}   on a line of its own

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "bold"; children: Inline[] }
  | { kind: "italic"; children: Inline[] }
  | { kind: "link"; target: string; label: string | null };

export type ImageAlign = "left" | "center" | "right" | "full";

export type Line =
  | { kind: "heading"; level: number; inlines: Inline[]; source: string }
  | { kind: "paragraph"; inlines: Inline[]; source: string }
  | { kind: "item"; inlines: Inline[]; source: string }
  | {
      kind: "image";
      mediaId: string;
      align: ImageAlign;
      width: number;
      caption: string;
      source: string;
    };

// Leftmost match wins, so `'''bold [[link]]'''` is bold with a link inside.
const INLINE = /\[\[([^\]]+)\]\]|'''(.+?)'''|''(.+?)''/g;
const HEADING = /^(={2,6})\s*(.*?)\s*=*\s*$/;
const ITEM = /^\*\s+/;
const IMAGE =
  /^\s*\{\{image:([a-f0-9]{32})\|(left|center|right|full)\|(\d{1,3})\|(.*?)\}\}\s*$/;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const at = match.index ?? 0;
    if (at > last) out.push({ kind: "text", text: text.slice(last, at) });
    const [, link, bold, italic] = match;
    if (link !== undefined) out.push(parseLink(link));
    else if (bold !== undefined) out.push({ kind: "bold", children: parseInline(bold) });
    else if (italic !== undefined)
      out.push({ kind: "italic", children: parseInline(italic) });
    last = at + match[0].length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out;
}

function parseLink(body: string): Inline {
  const pipe = body.indexOf("|");
  if (pipe === -1) return { kind: "link", target: body.trim(), label: null };
  return {
    kind: "link",
    target: body.slice(0, pipe).trim(),
    label: body.slice(pipe + 1).trim() || null,
  };
}

/** One entry per non-blank line: the unit the studio lets a writer pick up. */
export function parseLines(text: string): Line[] {
  const lines: Line[] = [];
  for (const raw of String(text ?? "").split(/\r?\n/)) {
    const source = raw.trimEnd();
    if (!source.trim()) continue;
    lines.push(parseLine(source));
  }
  return lines;
}

function parseLine(source: string): Line {
  const image = parseImage(source);
  if (image) return image;
  if (ITEM.test(source)) {
    return { kind: "item", inlines: parseInline(source.replace(ITEM, "")), source };
  }
  const heading = source.match(HEADING);
  if (heading) {
    return {
      kind: "heading",
      level: Math.min(heading[1]!.length, 6),
      inlines: parseInline(heading[2]!),
      source,
    };
  }
  return { kind: "paragraph", inlines: parseInline(source), source };
}

function parseImage(source: string): Line | null {
  const match = source.match(IMAGE);
  if (!match) return null;
  const align = match[2] as ImageAlign;
  const width = Number(match[3]);
  if (width < 10 || width > 100 || (align === "full" && width !== 100)) return null;
  return { kind: "image", mediaId: match[1]!, align, width, caption: match[4]!, source };
}

/** The same directive akasha/static/js/image-format.js writes. */
export function formatImage(image: {
  mediaId: string;
  align: ImageAlign;
  width: number;
  caption: string;
}): string {
  const width =
    image.align === "full" ? 100 : Math.max(10, Math.min(100, Math.round(image.width)));
  const caption = image.caption.replace(/\r?\n/g, " ").replaceAll("}}", "} }");
  return `{{image:${image.mediaId}|${image.align}|${width}|${caption}}}`;
}

/** Readable text with the markup gone; citations, which have no words, vanish. */
export function plainText(
  inlines: Inline[],
  isCitation: (target: string) => boolean,
): string {
  return inlines
    .map((inline) => {
      switch (inline.kind) {
        case "text":
          return inline.text;
        case "bold":
        case "italic":
          return plainText(inline.children, isCitation);
        case "link":
          if (isCitation(inline.target)) return "";
          return inline.label ?? inline.target.split("/").pop() ?? "";
      }
    })
    .join("")
    .replace(/\s+([.,;:!?])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

export type LineGroup =
  | { kind: "single"; line: Line; index: number }
  | { kind: "list"; items: { line: Line; index: number }[] };

/** Consecutive list items gathered into one list, so they render as one. */
export function groupLines(lines: Line[]): LineGroup[] {
  const groups: LineGroup[] = [];
  lines.forEach((line, index) => {
    const last = groups[groups.length - 1];
    if (line.kind !== "item") groups.push({ kind: "single", line, index });
    else if (last?.kind === "list") last.items.push({ line, index });
    else groups.push({ kind: "list", items: [{ line, index }] });
  });
  return groups;
}
