// One order of scenes in the editor, with its verdict and the controls that
// change it: the list itself, adding a scene at the end or after any row, and
// putting the dated scenes in time order. The editor shows one of these, or
// two side by side while an alternative is being tried.

import { useState, type ReactNode } from "react";
import type { EventSummary } from "../../api/types";
import { byTime } from "../../logic/plotline/order";
import { displayRows, type OrderRow } from "../../logic/plotline/rows";
import { Button } from "../../../components/ui/Button";
import { ProblemBanner, VerdictNotes } from "../../views/plotline/Findings";
import { AddScene } from "./Pickers";
import { SceneOrder } from "./SceneOrder";
import type { Preview } from "./usePreview";

export interface OrderColumnProps {
  book: string;
  label: string;
  heading?: ReactNode;
  order: string[];
  preview: Preview;
  known: ReadonlyMap<string, EventSummary>;
  terminus: string | null;
  continuationTitle: string | null;
  moved?: Set<string>;
  onOrder: (order: string[]) => void;
  onMove: (from: number, to: number) => void;
  onRemove: (index: number) => void;
  onAdd: (scene: EventSummary, at?: number) => void;
  onMakeEnding?: (row: OrderRow) => void;
  onEditScene?: (id: string) => void;
  /** Write a new scene to go at `at` (or the end). */
  onWriteNew?: (at?: number) => void;
  onJump: (scene: string) => void;
}

export function OrderColumn(props: OrderColumnProps) {
  // Where a scene picked next goes: after a row, or (null) at the end.
  const [insertAfter, setInsertAfter] = useState<number | null>(null);
  const rows = displayRows(props.order, props.preview.current, props.known);
  const verdict = props.preview.current;
  const add = (scene: EventSummary) => {
    props.onAdd(scene, insertAfter === null ? undefined : insertAfter + 1);
    setInsertAfter(null);
  };
  const afterTitle =
    insertAfter === null ? null : rows.find((r) => r.index === insertAfter)?.title;
  return (
    <section className="cw-order-column" aria-label={props.label}>
      <div className="cw-order-column-head">
        {props.heading ?? <h3 className="cw-section-title">{props.label}</h3>}
        <span
          className={`cw-order-status${props.preview.checking ? " is-checking" : ""}`}
          role="status"
        >
          {props.preview.checking
            ? "Checking…"
            : (props.preview.error ?? (verdict ? "Checked" : ""))}
        </span>
      </div>
      {verdict ? (
        <div className="cw-order-verdicts">
          <ProblemBanner
            events={verdict.effective_events}
            status={verdict.status}
            onJump={props.onJump}
            noun="order"
          />
          <VerdictNotes status={verdict.status} events={verdict.effective_events} />
        </div>
      ) : null}
      <SceneOrder
        book={props.book}
        rows={rows}
        label={props.label}
        terminus={props.terminus}
        continuationTitle={props.continuationTitle}
        moved={props.moved}
        onMove={props.onMove}
        onRemove={props.onRemove}
        onInsertAfter={setInsertAfter}
        onMakeEnding={props.onMakeEnding}
        onEditScene={props.onEditScene}
        onJump={props.onJump}
      />
      <div className="cw-order-actions">
        <AddScene
          key={insertAfter ?? "end"}
          label={afterTitle ? `Insert after “${afterTitle}”` : "Add a scene"}
          already={props.order}
          autoFocus={insertAfter !== null}
          onAdd={add}
          onWriteNew={
            props.onWriteNew
              ? () => {
                  props.onWriteNew?.(insertAfter === null ? undefined : insertAfter + 1);
                  setInsertAfter(null);
                }
              : undefined
          }
          onCancel={insertAfter === null ? undefined : () => setInsertAfter(null)}
        />
        {props.order.length > 1 ? (
          <Button
            size="sm"
            variant="ghost"
            icon="clock"
            title="Put the dated scenes in chronological order"
            onClick={() => props.onOrder(byTime(props.order, (id) => props.known.get(id)))}
          >
            Sort by time
          </Button>
        ) : null}
      </div>
    </section>
  );
}
