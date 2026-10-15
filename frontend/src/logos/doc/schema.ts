// The editor's schema: Logos's document vocabulary and nothing else, named as
// Logos names it, so `convert.ts` is a near-identity and a node the API would
// refuse cannot be typed or pasted in the first place.
//
//   doc            block+
//   paragraph      {id}          inline*
//   heading        {id, level}   inline*      level 1-3, drawn as h2-h4
//   bullet_list    {id}          list_item+
//   ordered_list   {id}          list_item+
//   list_item                    inline*      Logos lists hold prose, not blocks
//   text, hard_break
//   marks: em, strong, strike, code; link {href}; mention {kind, database,
//   collection, id}
//
// A mention is a *mark*, not an atom: a linked phrase is prose, selectable and
// editable word by word, exactly as the reader shows it. Links and mentions
// exclude every other mark because Logos's link and mention nodes carry none.

import { Mark, Node, mergeAttributes, type Extensions } from "@tiptap/core";
import { safeHref } from "./href";

const blockId = {
  id: {
    default: null as string | null,
    parseHTML: (element: HTMLElement) => element.getAttribute("data-block-id"),
    renderHTML: (attributes: { id?: string | null }) =>
      attributes.id ? { "data-block-id": attributes.id } : {},
  },
};

export const LogosDoc = Node.create({
  name: "doc",
  topNode: true,
  content: "block+",
});

export const Paragraph = Node.create({
  name: "paragraph",
  priority: 1000,
  group: "block",
  content: "inline*",
  addAttributes: () => blockId,
  parseHTML: () => [{ tag: "p" }],
  renderHTML: ({ HTMLAttributes }) => ["p", HTMLAttributes, 0],
});

const HEADING_TAGS = { 1: "h2", 2: "h3", 3: "h4" } as const;
const TAG_LEVELS: [string, 1 | 2 | 3][] = [
  ["h1", 1],
  ["h2", 1],
  ["h3", 2],
  ["h4", 3],
  ["h5", 3],
  ["h6", 3],
];

export const Heading = Node.create({
  name: "heading",
  group: "block",
  content: "inline*",
  defining: true,
  addAttributes: () => ({
    ...blockId,
    level: { default: 1, rendered: false },
  }),
  parseHTML: () => TAG_LEVELS.map(([tag, level]) => ({ tag, attrs: { level } })),
  renderHTML: ({ node, HTMLAttributes }) => [
    HEADING_TAGS[node.attrs.level as 1 | 2 | 3] ?? "h2",
    HTMLAttributes,
    0,
  ],
});

export const BulletList = Node.create({
  name: "bullet_list",
  group: "block",
  content: "list_item+",
  addAttributes: () => blockId,
  parseHTML: () => [{ tag: "ul" }],
  renderHTML: ({ HTMLAttributes }) => ["ul", HTMLAttributes, 0],
});

export const OrderedList = Node.create({
  name: "ordered_list",
  group: "block",
  content: "list_item+",
  addAttributes: () => blockId,
  parseHTML: () => [{ tag: "ol" }],
  renderHTML: ({ HTMLAttributes }) => ["ol", HTMLAttributes, 0],
});

export const ListItem = Node.create({
  name: "list_item",
  content: "inline*",
  defining: true,
  parseHTML: () => [
    {
      tag: "li",
      // Other editors wrap an item's words in a <p>; Logos items are the words.
      contentElement: (element: HTMLElement) =>
        element.querySelector(":scope > p") ?? element,
    },
  ],
  renderHTML: () => ["li", 0],
});

export const Text = Node.create({ name: "text", group: "inline" });

export const HardBreak = Node.create({
  name: "hard_break",
  group: "inline",
  inline: true,
  selectable: false,
  parseHTML: () => [{ tag: "br" }],
  renderHTML: () => ["br"],
  addKeyboardShortcuts() {
    const insert = () => this.editor.commands.insertContent({ type: this.name });
    return { "Shift-Enter": insert, "Mod-Enter": insert };
  },
});

function simpleMark(
  name: string,
  tag: string,
  tags: string[],
  shortcut: string,
  style?: string,
) {
  return Mark.create({
    name,
    parseHTML: () => [...tags.map((t) => ({ tag: t })), ...(style ? [{ style }] : [])],
    renderHTML: ({ HTMLAttributes }) => [tag, HTMLAttributes, 0],
    addKeyboardShortcuts() {
      return { [shortcut]: () => this.editor.commands.toggleMark(this.name) };
    },
  });
}

// Order matters: ProseMirror keeps marks in schema order, which is the order
// Logos writes them in (`MARK_ORDER`).
export const Em = simpleMark("em", "em", ["em", "i"], "Mod-i", "font-style=italic");
export const Strong = Mark.create({
  name: "strong",
  parseHTML: () => [
    { tag: "strong" },
    // Google Docs wraps everything in <b style="font-weight:normal">.
    {
      tag: "b",
      getAttrs: (node: HTMLElement) => node.style.fontWeight !== "normal" && null,
    },
    {
      style: "font-weight",
      getAttrs: (value: string) => /^(bold(er)?|[6-9]\d{2})$/.test(value) && null,
    },
  ],
  renderHTML: ({ HTMLAttributes }) => ["strong", HTMLAttributes, 0],
  addKeyboardShortcuts() {
    return { "Mod-b": () => this.editor.commands.toggleMark(this.name) };
  },
});
export const Strike = simpleMark(
  "strike",
  "del",
  ["del", "s", "strike"],
  "Mod-Shift-s",
  "text-decoration=line-through",
);
export const Code = simpleMark("code", "code", ["code"], "Mod-e");

export const Link = Mark.create({
  name: "link",
  inclusive: false,
  excludes: "_",
  addAttributes: () => ({ href: { default: null } }),
  parseHTML: () => [
    {
      tag: "a[href]",
      getAttrs: (node: HTMLElement) => {
        const href = safeHref(node.getAttribute("href"));
        return href ? { href } : false;
      },
    },
  ],
  renderHTML: ({ HTMLAttributes }) => [
    "a",
    mergeAttributes(HTMLAttributes, { rel: "noopener noreferrer nofollow" }),
    0,
  ],
});

export const Mention = Mark.create({
  name: "mention",
  inclusive: false,
  excludes: "_",
  addAttributes: () => ({
    kind: {
      default: "mention",
      parseHTML: (el: HTMLElement) => el.getAttribute("data-entity-type") ?? "mention",
      renderHTML: (attrs: { kind: string }) => ({ "data-entity-type": attrs.kind }),
    },
    database: {
      default: "",
      parseHTML: (el: HTMLElement) => el.getAttribute("data-database"),
      renderHTML: (attrs: { database: string }) => ({ "data-database": attrs.database }),
    },
    collection: {
      default: "",
      parseHTML: (el: HTMLElement) => el.getAttribute("data-collection"),
      renderHTML: (attrs: { collection: string }) => ({
        "data-collection": attrs.collection,
      }),
    },
    id: {
      default: "",
      parseHTML: (el: HTMLElement) => el.getAttribute("data-entity-id"),
      renderHTML: (attrs: { id: string }) => ({ "data-entity-id": attrs.id }),
    },
  }),
  parseHTML: () => [{ tag: "span[data-entity-id]" }],
  renderHTML: ({ HTMLAttributes }) => [
    "span",
    mergeAttributes(HTMLAttributes, { class: "entity-mention" }),
    0,
  ],
});

/** Every node and mark of the schema, in the order ProseMirror should rank them. */
export const schemaExtensions: Extensions = [
  LogosDoc,
  Paragraph,
  Heading,
  BulletList,
  OrderedList,
  ListItem,
  Text,
  HardBreak,
  Em,
  Strong,
  Strike,
  Code,
  Link,
  Mention,
];
