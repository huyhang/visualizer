// The calendar rail and simultaneous scenes. Ported from layout.js's
// applyPeriodGrouping: coarse calendar components (Year, Month, ...) become
// period headings, and only the fine part stays on each row -- the way a
// thread's own timeline reads.
//
// The unit of vertical space is a **slot**, not a node: scenes starting on the
// same tick share one, so they share one y. Stacked, a vertical timeline reads
// as "this, then that" -- an order that is not in the story, only an
// alphabetical tie-break. (A thread's own scenes can never share a tick, so
// this only ever groups across threads, which is what a map is for.)

import { groupByPeriod } from "../timeaxis";
import {
  geometry,
  type LaidEdge,
  type LaidNode,
  type LaneMeta,
  type Layout,
} from "./layout";

export interface Header {
  level: number;
  label: string;
  y: number;
}

export interface Slot {
  id: string;
  nodes: LaidNode[];
  /** Several scenes at one moment. */
  isGroup?: boolean;
  count?: number;
  /** A moment whose scenes the writer hid behind their count. */
  collapsed?: boolean;
  top: number;
  y: number;
  bottom: number;
  when?: string;
}

/** Headings and rows, in the order they are drawn. */
export type Entry = { kind: "header"; header: Header } | { kind: "row"; row: Slot };

export interface MapModel {
  headers: Header[];
  rows: Slot[];
  sequence: Entry[];
  nodes: (LaidNode & { when?: string })[];
  edges: LaidEdge[];
  lanes: LaneMeta[];
  width: number;
  minWidth: number;
  height: number;
}

/** Stable while the coincidence lasts: its tick and first scene name it. */
export const groupId = (nodes: LaidNode[]) => `~at:${nodes[0]?.startTick}:${nodes[0]?.id}`;

type Pending = { header: { level: number; label: string } } | { node: LaidNode };
type Batched =
  | { header: { level: number; label: string } }
  | {
      id: string;
      nodes: LaidNode[];
      isGroup?: boolean;
      count?: number;
      collapsed?: boolean;
    };

/** Batch consecutive rows starting on one tick into one slot; an undated scene never groups. */
export function slots(sequence: Pending[], collapsed: Set<string>): Batched[] {
  const out: Batched[] = [];
  let run: LaidNode[] = [];
  const flush = () => {
    if (run.length > 1) {
      const id = groupId(run);
      out.push({
        id,
        nodes: [...run],
        isGroup: true,
        count: run.length,
        collapsed: collapsed.has(id),
      });
    } else if (run.length === 1) {
      out.push({ id: run[0]?.id ?? "", nodes: [...run] });
    }
    run = [];
  };
  for (const item of sequence) {
    if ("header" in item) {
      flush();
      out.push(item);
      continue;
    }
    const n = item.node;
    if (!n.scheduled || n.startTick === null) {
      flush();
      out.push({ id: n.id, nodes: [n] });
    } else if (run.length && run[run.length - 1]?.startTick === n.startTick) run.push(n);
    else {
      flush();
      run = [n];
    }
  }
  flush();
  return out;
}

export function applyPeriodGrouping(
  layout: Layout,
  opts: {
    heightOf?: (slot: { id: string }) => number;
    collapsedMoments?: Set<string>;
  } = {},
): MapModel {
  const heightOf = opts.heightOf ?? (() => geometry.ROW_H);
  const collapsed = opts.collapsedMoments ?? new Set<string>();
  const ordered = [...layout.nodes].sort((a, b) => a.row - b.row);
  const adapters = ordered.map((n) => ({
    scheduled: n.scheduled,
    start_label: n.startLabel,
    end_label: n.endLabel,
    start_parts: n.startParts,
    end_parts: n.endParts,
    node: n,
  }));

  const when = new Map<string, string>();
  const pending: Pending[] = groupByPeriod(adapters).map((item) => {
    if (item.type === "header") return { header: { level: item.level, label: item.label } };
    when.set(item.event.node.id, item.label);
    return { node: item.event.node };
  });

  const headers: Header[] = [];
  const rows: Slot[] = [];
  const sequence: Entry[] = [];
  let y: number = geometry.PAD_TOP;
  for (const slot of slots(pending, collapsed)) {
    if ("header" in slot) {
      const header = { ...slot.header, y };
      headers.push(header);
      sequence.push({ kind: "header", header });
      y += geometry.HEADER_H;
      continue;
    }
    const h = heightOf(slot.isGroup ? slot : (slot.nodes[0] as LaidNode));
    const row: Slot = {
      ...slot,
      top: y,
      y: y + h / 2,
      bottom: y + h,
      when: when.get(slot.nodes[0]?.id ?? ""),
    };
    rows.push(row);
    sequence.push({ kind: "row", row });
    y += h;
  }

  const cy = new Map<string, number>();
  rows.forEach((slot) => slot.nodes.forEach((n) => cy.set(n.id, slot.y)));
  const nodes = ordered.map((n) => ({ ...n, y: cy.get(n.id) ?? 0, when: when.get(n.id) }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  rows.forEach((slot) => (slot.nodes = slot.nodes.map((n) => byId.get(n.id) ?? n)));
  const edges = layout.edges.map((e) => ({
    ...e,
    y1: cy.get(e.from) ?? 0,
    y2: cy.get(e.to) ?? 0,
  }));
  return {
    headers,
    rows,
    sequence,
    nodes,
    edges,
    lanes: layout.lanes,
    width: layout.width,
    minWidth: layout.minWidth,
    height: y + 8,
  };
}
