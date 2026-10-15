// Builders for Logos documents and ProseMirror nodes in tests.

import { getSchema } from "@tiptap/core";
import type { Node as PmNode } from "@tiptap/pm/model";
import { logosToPm } from "../doc/convert";
import { schemaExtensions } from "../doc/schema";
import type { Block, Inline, LogosDocument } from "../doc/types";

export const schema = getSchema(schemaExtensions);

export const text = (
  value: string,
  ...marks: ("em" | "strong" | "strike" | "code")[]
): Inline =>
  marks.length
    ? { type: "text", text: value, marks: marks.map((type) => ({ type })) }
    : { type: "text", text: value };

export const mention = (value: string, id = "lyra"): Inline => ({
  type: "mention",
  text: value,
  ref: { database: "ember", collection: "characters", id },
});

export const para = (id: string, ...content: Inline[]): Block => ({
  type: "paragraph",
  id,
  content,
});

export const doc = (...content: Block[]): LogosDocument => ({
  version: 1,
  type: "doc",
  content,
});

export const pmDoc = (document: LogosDocument): PmNode =>
  schema.nodeFromJSON(logosToPm(document, () => "fresh"));
