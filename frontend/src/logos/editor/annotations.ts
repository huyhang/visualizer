// Review issues and Coach findings, drawn over the prose they are about.
//
// An annotation names a block and a quoted phrase. This plugin finds the
// phrase in the document as it is *now* and underlines it with a decoration --
// paint, not content: it never enters the saved document, follows every edit,
// and disappears when the words it quoted are rewritten (the issue is then
// "unplaced", which the panel shows as stale). Each annotated paragraph also
// gets a quiet marker in its margin.
//
// The plugin knows nothing about reviews or the Coach. What it reports -- a
// click on an underline, where everything landed -- goes through an injected
// `AnnotationBridge`, which the React side fills in.

import { Extension } from "@tiptap/core";
import type { Node as PmNode } from "@tiptap/pm/model";
import { Plugin, PluginKey, type EditorState, type Transaction } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { findBlock, quoteRange, type Range } from "./positions";

export type AnnotationSource = "coach" | "editor";

export interface Annotation {
  /** Unique across sources. */
  id: string;
  source: AnnotationSource;
  /** What sort of note: a review check, or a Coach category. */
  kind: string;
  severity: "info" | "warning";
  blockId: string;
  quote: string;
}

export type Placement = Record<string, Range | null>;

export interface AnnotationBridge {
  /** An underline was clicked; `anchor` is its element, for a popover to point at. */
  onActivate: (id: string, anchor: HTMLElement) => void;
  /** Where every annotation landed after a change; null for one whose words are gone. */
  onPlacement: (placement: Placement) => void;
}

interface AnnotationState {
  annotations: Annotation[];
  active: string | null;
  placement: Placement;
  decorations: DecorationSet;
}

interface AnnotationMeta {
  annotations?: Annotation[];
  active?: string | null;
}

export const annotationsKey = new PluginKey<AnnotationState>("logos-annotations");

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    logosAnnotations: {
      setAnnotations: (annotations: Annotation[]) => ReturnType;
      setActiveAnnotation: (id: string | null) => ReturnType;
    };
  }
}

/** Where each annotation's quote is in `doc`. */
export function place(doc: PmNode, annotations: Annotation[]): Placement {
  const placement: Placement = {};
  for (const annotation of annotations) {
    placement[annotation.id] = quoteRange(doc, annotation.blockId, annotation.quote);
  }
  return placement;
}

// A paragraph's margin mark speaks for its strongest note: an editor's warning,
// then an editor's note, then the Coach.
const rank = (a: Annotation) =>
  a.source === "coach" ? 1 : a.severity === "warning" ? 3 : 2;

/** The decorations for annotations at `placement`, the active one marked. */
export function decorate(
  doc: PmNode,
  annotations: Annotation[],
  placement: Placement,
  active: string | null,
): DecorationSet {
  const decorations: Decoration[] = [];
  const strongest = new Map<string, Annotation>();
  for (const annotation of annotations) {
    const range = placement[annotation.id];
    if (!range) continue;
    const classes = [
      "logos-ann",
      `logos-ann-${annotation.source}`,
      `logos-ann-${annotation.severity}`,
      `logos-ann-k-${annotation.kind.replace(/[^a-z0-9-]/gi, "-").toLowerCase()}`,
      annotation.id === active ? "is-active" : "",
    ].filter(Boolean);
    decorations.push(
      Decoration.inline(range.from, range.to, {
        class: classes.join(" "),
        "data-annotation": annotation.id,
      }),
    );
    const held = strongest.get(annotation.blockId);
    if (!held || rank(annotation) > rank(held))
      strongest.set(annotation.blockId, annotation);
  }
  for (const [blockId, note] of strongest) {
    const block = findBlock(doc, blockId);
    if (block) {
      decorations.push(
        Decoration.node(block.pos, block.pos + block.node.nodeSize, {
          class: "logos-annotated",
          "data-annotated": note.source,
          "data-annotated-kind": note.source === "coach" ? "coach" : note.kind,
          "data-annotated-severity": note.severity,
        }),
      );
    }
  }
  return DecorationSet.create(doc, decorations);
}

function build(
  doc: PmNode,
  annotations: Annotation[],
  active: string | null,
): AnnotationState {
  const placement = place(doc, annotations);
  return {
    annotations,
    active,
    placement,
    decorations: decorate(doc, annotations, placement, active),
  };
}

function next(tr: Transaction, previous: AnnotationState): AnnotationState {
  const meta = tr.getMeta(annotationsKey) as AnnotationMeta | undefined;
  if (!meta && !tr.docChanged) return previous;
  const annotations = meta?.annotations ?? previous.annotations;
  const active = meta && "active" in meta ? (meta.active ?? null) : previous.active;
  return build(tr.doc, annotations, active);
}

/** The annotation state an editor holds, for code that needs to read it. */
export const annotationState = (state: EditorState) => annotationsKey.getState(state);

export const Annotations = Extension.create<{ bridge: AnnotationBridge }>({
  name: "logosAnnotations",
  addOptions: () => ({ bridge: { onActivate: () => {}, onPlacement: () => {} } }),
  addCommands() {
    return {
      setAnnotations:
        (annotations) =>
        ({ tr, dispatch }) => {
          if (dispatch)
            tr.setMeta(annotationsKey, { annotations }).setMeta("addToHistory", false);
          return true;
        },
      setActiveAnnotation:
        (active) =>
        ({ tr, dispatch }) => {
          if (dispatch)
            tr.setMeta(annotationsKey, { active }).setMeta("addToHistory", false);
          return true;
        },
    };
  },
  addProseMirrorPlugins() {
    const { bridge } = this.options;
    return [
      new Plugin<AnnotationState>({
        key: annotationsKey,
        state: {
          init: (_config, state) => build(state.doc, [], null),
          apply: (tr, previous) => next(tr, previous),
        },
        props: {
          decorations: (state) => annotationsKey.getState(state)?.decorations,
          handleClick(_view, _pos, event) {
            const target = event.target instanceof Element ? event.target : null;
            const anchor = target?.closest<HTMLElement>("[data-annotation]");
            if (!anchor?.dataset.annotation) return false;
            bridge.onActivate(anchor.dataset.annotation, anchor);
            return false;
          },
        },
        view: () => ({
          update(view, previous) {
            const now = annotationsKey.getState(view.state);
            if (now && now.placement !== annotationsKey.getState(previous)?.placement) {
              bridge.onPlacement(now.placement);
            }
          },
        }),
      }),
    ];
  },
});
