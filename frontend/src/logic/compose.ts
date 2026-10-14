// The note being composed: an ordered list of blocks, and what saving it sends.
//
// Pure, so every rule can be tested without React. Block ids come from an
// injected generator for the same reason. A composition targets either a new
// note or an existing one, whose body arrives as one editable block and whose
// revision travels with the save so a note changed meanwhile is refused.

import type { NoteRequest } from "../api/types";
import { INBOX } from "./citations";
import { formatImage, type ImageAlign } from "./wikitext";

export type NewId = () => string;

export interface TextBlock {
  id: string;
  kind: "text";
  text: string;
  /** The inbox draft slug it came from, or null for the writer's own words. */
  draft: string | null;
  /** The body the existing note had when it was opened. */
  existing?: boolean;
}

export interface ImageBlock {
  id: string;
  kind: "image";
  draft: string;
  index: number;
  caption: string;
  previewUrl: string;
  mediaId: string | null;
  align: ImageAlign;
  width: number;
}

export type NoteBlock = TextBlock | ImageBlock;

export type Target = { kind: "new" } | { kind: "existing"; slug: string; rev: number };

export interface Composition {
  target: Target;
  title: string;
  blocks: NoteBlock[];
}

export function emptyComposition(): Composition {
  return { target: { kind: "new" }, title: "", blocks: [] };
}

/** Start composing on top of an existing note; material added so far is kept. */
export function onExisting(
  comp: Composition,
  note: { slug: string; rev: number; title: string; body: string },
  newId: NewId,
): Composition {
  const added = withoutExisting(comp.blocks);
  const existing: TextBlock = {
    id: newId(),
    kind: "text",
    text: note.body,
    draft: null,
    existing: true,
  };
  return {
    target: { kind: "existing", slug: note.slug, rev: note.rev },
    title: note.title,
    blocks: note.body.trim() ? [existing, ...added] : added,
  };
}

/** Back to a new note, keeping what was added -- but not the old note's text. */
export function onNew(comp: Composition): Composition {
  return {
    target: { kind: "new" },
    title: comp.target.kind === "existing" ? "" : comp.title,
    blocks: withoutExisting(comp.blocks),
  };
}

function withoutExisting(blocks: NoteBlock[]): NoteBlock[] {
  return blocks.filter((b) => b.kind === "image" || !b.existing);
}

export function addText(
  comp: Composition,
  text: string,
  draft: string | null,
  newId: NewId,
): Composition {
  if (!text.trim()) return comp;
  return { ...comp, blocks: [...comp.blocks, { id: newId(), kind: "text", text, draft }] };
}

export function addImage(
  comp: Composition,
  image: {
    draft: string;
    index: number;
    caption: string;
    previewUrl: string;
    mediaId: string | null;
  },
  newId: NewId,
): Composition {
  if (hasImage(comp, image.draft, image.index)) return comp;
  const block: ImageBlock = {
    id: newId(),
    kind: "image",
    align: "right",
    width: 40,
    ...image,
  };
  return { ...comp, blocks: [...comp.blocks, block] };
}

export function updateBlock(
  comp: Composition,
  id: string,
  patch: Partial<Omit<TextBlock, "id" | "kind">> | Partial<Omit<ImageBlock, "id" | "kind">>,
): Composition {
  return {
    ...comp,
    blocks: comp.blocks.map((b) => (b.id === id ? ({ ...b, ...patch } as NoteBlock) : b)),
  };
}

export function moveBlock(comp: Composition, id: string, delta: number): Composition {
  const from = comp.blocks.findIndex((b) => b.id === id);
  const to = from + delta;
  if (from === -1 || to < 0 || to >= comp.blocks.length) return comp;
  const blocks = comp.blocks.slice();
  const [moved] = blocks.splice(from, 1);
  blocks.splice(to, 0, moved!);
  return { ...comp, blocks };
}

export function removeBlock(comp: Composition, id: string): Composition {
  return { ...comp, blocks: comp.blocks.filter((b) => b.id !== id) };
}

export function setTitle(comp: Composition, title: string): Composition {
  return { ...comp, title };
}

/** Whether this exact text is already in the note -- "Added" on a passage. */
export function hasText(comp: Composition, text: string): boolean {
  const wanted = text.trim();
  return comp.blocks.some((b) => b.kind === "text" && b.text.includes(wanted));
}

export function hasImage(comp: Composition, draft: string, index: number): boolean {
  return comp.blocks.some(
    (b) => b.kind === "image" && b.draft === draft && b.index === index,
  );
}

/** How many blocks were added to the note: the count on the "Note" tab. */
export function addedCount(comp: Composition): number {
  return withoutExisting(comp.blocks).length;
}

/** Images that must be imported into the world's library before saving. */
export function pendingImages(comp: Composition): ImageBlock[] {
  return comp.blocks.filter((b): b is ImageBlock => b.kind === "image" && !b.mediaId);
}

/** Blank title, or nothing but blank blocks: there is no note to save. */
export function problem(comp: Composition): string | null {
  if (!comp.title.trim()) return "Give the note a title.";
  const anything = comp.blocks.some((b) => b.kind === "image" || b.text.trim());
  return anything ? null : "Add something to the note first.";
}

/** The wikitext a composition saves as. Every image must have its media id. */
export function bodyOf(comp: Composition): string {
  return comp.blocks
    .map((b) => {
      if (b.kind === "text") return b.text.trim();
      if (!b.mediaId) throw new Error(`Image ${b.index} has not been imported yet.`);
      return formatImage({
        mediaId: b.mediaId,
        align: b.align,
        width: b.width,
        caption: b.caption,
      });
    })
    .filter(Boolean)
    .join("\n\n");
}

/** The inbox drafts the note took material from, recorded on their jobs. */
export function draftsOf(comp: Composition): string[] {
  const slugs = comp.blocks.map((b) => b.draft).filter((d): d is string => !!d);
  return [...new Set(slugs)].map((slug) => `${INBOX}/${slug}`);
}

export function noteRequest(comp: Composition): NoteRequest {
  const request: NoteRequest = {
    title: comp.title.trim(),
    body: bodyOf(comp),
    drafts: draftsOf(comp),
  };
  if (comp.target.kind === "existing") {
    request.note = comp.target.slug;
    request.rev = comp.target.rev;
  }
  return request;
}

/** Record imported images, so a failed save does not import them twice. */
export function withMedia(
  comp: Composition,
  media: ReadonlyMap<string, string>,
): Composition {
  return {
    ...comp,
    blocks: comp.blocks.map((b) =>
      b.kind === "image" && media.has(b.id) ? { ...b, mediaId: media.get(b.id)! } : b,
    ),
  };
}

/** An empty block for the writer's own words. */
export function addBlank(
  comp: Composition,
  newId: NewId,
): { comp: Composition; id: string } {
  const id = newId();
  return {
    comp: {
      ...comp,
      blocks: [...comp.blocks, { id, kind: "text", text: "", draft: null }],
    },
    id,
  };
}

/** The composition without these blocks: what is left once they are saved. */
export function withoutBlocks(comp: Composition, ids: ReadonlySet<string>): Composition {
  return { ...comp, blocks: comp.blocks.filter((b) => !ids.has(b.id)) };
}
