// Curly quotes as the writer types and pastes, so the page shows what will be
// stored. Two moments, two rules (see `doc/typography.ts`): a typed mark is
// decided from the text behind the caret, and a leading apostrophe guessed as
// an opening quote is corrected as its word lands; pasted prose arrives whole,
// so it gets the careful rule that looks both ways. Code keeps its marks.

import { Extension } from "@tiptap/core";
import { Fragment, Slice, type Node as PmNode } from "@tiptap/pm/model";
import { Plugin, PluginKey, type EditorState } from "@tiptap/pm/state";
import { curlText, curlTypedMark, fixElisions } from "../doc/typography";

export const smartQuotesKey = new PluginKey("logos-smart-quotes");

const inCode = (state: EditorState, pos: number) =>
  state.doc
    .resolve(pos)
    .marks()
    .some((mark) => mark.type.name === "code") ||
  (state.storedMarks ?? []).some((mark) => mark.type.name === "code");

/** The text typed at `from` as it should land, with what precedes it in its block. */
export function typedText(before: string, typed: string): string {
  if (typed === '"' || typed === "'") return curlTypedMark(before, typed);
  return typed;
}

/** Offsets in `text` whose ‘ should now read ’ (a completed elision). */
export function elisionsIn(text: string): number[] {
  const fixed = fixElisions(text);
  const offsets: number[] = [];
  for (let i = 0; i < text.length; i += 1) if (fixed[i] !== text[i]) offsets.push(i);
  return offsets;
}

function curlFragment(fragment: Fragment): Fragment {
  const nodes: PmNode[] = [];
  fragment.forEach((node, _offset, index) => {
    if (node.isText) {
      if (node.marks.some((mark) => mark.type.name === "code")) {
        nodes.push(node);
        return;
      }
      const before = index > 0 ? (fragment.child(index - 1).text ?? "").slice(-1) : "";
      const after =
        index + 1 < fragment.childCount
          ? ((fragment.child(index + 1).text ?? "")[0] ?? "")
          : "";
      nodes.push(
        node.type.schema.text(curlText(node.text ?? "", before, after), node.marks),
      );
    } else {
      nodes.push(node.copy(curlFragment(node.content)));
    }
  });
  return Fragment.from(nodes);
}

/** A pasted slice with its straight marks curled. */
export function curlSlice(slice: Slice): Slice {
  return new Slice(curlFragment(slice.content), slice.openStart, slice.openEnd);
}

export const SmartQuotes = Extension.create({
  name: "smartQuotes",
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: smartQuotesKey,
        props: {
          handleTextInput(view, from, to, typed) {
            const { state } = view;
            if (view.composing || inCode(state, from)) return false;
            const $from = state.doc.resolve(from);
            const blockStart = $from.start();
            const before = state.doc.textBetween(blockStart, from, undefined, "￼");
            const landed = typedText(before, typed);
            const after = before + landed;
            const elided = elisionsIn(after);
            if (landed === typed && !elided.length) return false;
            const tr = state.tr.insertText(landed, from, to);
            for (const offset of elided) {
              const pos = blockStart + offset;
              tr.insertText("’", pos, pos + 1);
            }
            view.dispatch(tr);
            return true;
          },
          transformPasted: (slice) => curlSlice(slice),
        },
      }),
    ];
  },
});
