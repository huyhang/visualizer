// Logos's stored rich text, exactly as `logos/richtext.py` validates it. The
// editor works on ProseMirror's own tree; `convert.ts` is the only place the
// two meet.

export type MarkType = "em" | "strong" | "strike" | "code";
export const MARK_ORDER: readonly MarkType[] = ["em", "strong", "strike", "code"];

export interface ArticleRef {
  database: string;
  collection: string;
  id: string;
}

export interface TextNode {
  type: "text";
  text: string;
  marks?: { type: MarkType }[];
}

export interface LinkNode {
  type: "link";
  href: string;
  text: string;
}

export interface ReferenceNode {
  type: "mention" | "article_link";
  text: string;
  ref: ArticleRef;
}

export interface HardBreak {
  type: "hard_break";
}

export type Inline = TextNode | LinkNode | ReferenceNode | HardBreak;

export interface Paragraph {
  type: "paragraph";
  id: string;
  content: Inline[];
}

export interface Heading {
  type: "heading";
  id: string;
  level: 1 | 2 | 3;
  content: Inline[];
}

export interface ListItem {
  type: "list_item";
  content: Inline[];
}

export interface List {
  type: "bullet_list" | "ordered_list";
  id: string;
  content: ListItem[];
}

export type Block = Paragraph | Heading | List;

export interface LogosDocument {
  version: 1;
  type: "doc";
  content: Block[];
}

export const isList = (block: Block): block is List =>
  block.type === "bullet_list" || block.type === "ordered_list";

export const emptyDocument = (): LogosDocument => ({
  version: 1,
  type: "doc",
  content: [],
});
