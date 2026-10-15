// Logos documents <-> ProseMirror JSON. The only place the two shapes meet.
//
// Stored prose is the source of truth. Going in, Logos's link and mention
// nodes become text carrying a `link` or `mention` mark; coming out, they turn
// back into nodes, adjacent runs that differ only in their words merge (what
// the old editor's `compact` did), ids are made unique, and quotes are curled
// as the server will curl them anyway.

import type { JSONContent } from "@tiptap/core";
import { newBlockId, uniqueIds, type IdFactory } from "./ids";
import { curlDocument } from "./typography";
import {
  MARK_ORDER,
  isList,
  type ArticleRef,
  type Block,
  type Inline,
  type LogosDocument,
  type MarkType,
} from "./types";

/** What the server accepts in one text node (`MAX_TEXT_LENGTH`). */
export const MAX_TEXT = 10_000;

// -- in ------------------------------------------------------------------------

function inlineToPm(node: Inline): JSONContent {
  switch (node.type) {
    case "hard_break":
      return { type: "hard_break" };
    case "link":
      return {
        type: "text",
        text: node.text,
        marks: [{ type: "link", attrs: { href: node.href } }],
      };
    case "mention":
    case "article_link":
      return {
        type: "text",
        text: node.text,
        marks: [{ type: "mention", attrs: { kind: node.type, ...node.ref } }],
      };
    default:
      return node.marks?.length
        ? { type: "text", text: node.text, marks: node.marks.map(({ type }) => ({ type })) }
        : { type: "text", text: node.text };
  }
}

const withContent = (node: JSONContent, content: JSONContent[]) =>
  content.length ? { ...node, content } : node;

function blockToPm(block: Block): JSONContent {
  if (isList(block)) {
    const items = block.content.length
      ? block.content
      : [{ type: "list_item", content: [] }];
    return {
      type: block.type,
      attrs: { id: block.id },
      content: items.map((item) =>
        withContent({ type: "list_item" }, item.content.map(inlineToPm)),
      ),
    };
  }
  const attrs =
    block.type === "heading" ? { id: block.id, level: block.level } : { id: block.id };
  return withContent({ type: block.type, attrs }, block.content.map(inlineToPm));
}

/** A stored document as the editor's content. An empty one becomes one empty paragraph. */
export function logosToPm(
  document: LogosDocument,
  makeId: IdFactory = newBlockId,
): JSONContent {
  const content = document.content.map(blockToPm);
  return {
    type: "doc",
    content: content.length ? content : [{ type: "paragraph", attrs: { id: makeId() } }],
  };
}

// -- out -----------------------------------------------------------------------

type PmMark = NonNullable<JSONContent["marks"]>[number];

function inlineFromPm(node: JSONContent): Inline | null {
  if (node.type === "hard_break") return { type: "hard_break" };
  if (node.type !== "text" || !node.text) return null;
  const marks: PmMark[] = node.marks ?? [];
  const mention = marks.find((mark) => mark.type === "mention");
  if (mention) {
    const { kind, database, collection, id } = mention.attrs ?? {};
    const ref: ArticleRef = { database, collection, id };
    return {
      type: kind === "article_link" ? "article_link" : "mention",
      text: node.text,
      ref,
    };
  }
  const link = marks.find((mark) => mark.type === "link");
  if (link?.attrs?.href) return { type: "link", href: link.attrs.href, text: node.text };
  const kinds = MARK_ORDER.filter((kind) => marks.some((mark) => mark.type === kind));
  return kinds.length
    ? { type: "text", text: node.text, marks: kinds.map((type: MarkType) => ({ type })) }
    : { type: "text", text: node.text };
}

const sameButText = (left: Inline, right: Inline) => {
  const strip = (node: Inline) => JSON.stringify({ ...node, text: undefined });
  return "text" in left && "text" in right && strip(left) === strip(right);
};

/** Adjacent runs that differ only in their words become one; long ones are cut to size. */
export function compactInline(nodes: Inline[]): Inline[] {
  const merged: Inline[] = [];
  for (const node of nodes) {
    const previous = merged.at(-1);
    if (previous && "text" in previous && "text" in node && sameButText(previous, node)) {
      merged[merged.length - 1] = { ...previous, text: previous.text + node.text };
    } else {
      merged.push(node);
    }
  }
  return merged.flatMap((node): Inline[] => ("text" in node ? splitLong(node) : [node]));
}

function splitLong<T extends Inline & { text: string }>(node: T): T[] {
  if (node.text.length <= MAX_TEXT) return [node];
  const parts: T[] = [];
  for (let at = 0; at < node.text.length; at += MAX_TEXT) {
    parts.push({ ...node, text: node.text.slice(at, at + MAX_TEXT) });
  }
  return parts;
}

const inlineList = (content: JSONContent[] | undefined) =>
  compactInline((content ?? []).map(inlineFromPm).filter((n): n is Inline => n !== null));

function blockFromPm(node: JSONContent, id: string): Block | null {
  switch (node.type) {
    case "heading": {
      const level = [1, 2, 3].includes(node.attrs?.level) ? node.attrs?.level : 1;
      return { type: "heading", id, level, content: inlineList(node.content) };
    }
    case "bullet_list":
    case "ordered_list":
      return {
        type: node.type,
        id,
        content: (node.content ?? []).map((item) => ({
          type: "list_item",
          content: inlineList(item.content),
        })),
      };
    case "paragraph":
      return { type: "paragraph", id, content: inlineList(node.content) };
    default:
      return null;
  }
}

/** The editor's content as Logos stores it. */
export function pmToLogos(
  json: JSONContent,
  makeId: IdFactory = newBlockId,
): LogosDocument {
  const nodes = json.content ?? [];
  const ids = uniqueIds(
    nodes.map((node) => node.attrs?.id),
    makeId,
  );
  const content = nodes
    .map((node, index) => blockFromPm(node, ids[index] as string))
    .filter((block): block is Block => block !== null);
  return curlDocument({ version: 1, type: "doc", content });
}
