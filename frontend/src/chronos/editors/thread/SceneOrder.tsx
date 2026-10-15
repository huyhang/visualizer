// A thread's scenes as the editor shows them: in order, each with what the
// server says about it, and every way of rearranging them -- drag a row, or
// focus it and press ↑ / ↓ (with or without Alt), Delete to take it out.
// Inherited scenes are shown where they fall but locked: they are stored on
// the thread this one continues into, and an edit has to go there.

import { useEffect, useRef, useState, type DragEvent, type KeyboardEvent } from "react";
import { dropIndex, keyMove } from "../../logic/plotline/order";
import type { OrderRow } from "../../logic/plotline/rows";
import { markerOf } from "../../logic/plotline/verdicts";
import { FindingList } from "../../views/plotline/Findings";
import { sceneElement } from "../../views/plotline/useJump";
import { Badge } from "../../../components/ui/Badge";
import { IconButton } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";

export interface SceneOrderProps {
  book: string;
  rows: OrderRow[];
  /** What the list is called, for screen readers: "Scenes", "Alternative order". */
  label: string;
  /** The book's ending, marked wherever it falls. */
  terminus: string | null;
  continuationTitle: string | null;
  /** Scenes that sit somewhere else in the other order being compared. */
  moved?: Set<string>;
  onMove: (from: number, to: number) => void;
  onRemove: (index: number) => void;
  onInsertAfter?: (index: number) => void;
  onMakeEnding?: (row: OrderRow) => void;
  onEditScene?: (id: string) => void;
  onJump: (scene: string) => void;
}

const isBelowMidpoint = (e: DragEvent<HTMLElement>) => {
  const box = e.currentTarget.getBoundingClientRect();
  return e.clientY > box.top + box.height / 2;
};

function RowTools({ row, props }: { row: OrderRow; props: SceneOrderProps }) {
  const index = row.index ?? 0;
  const last = props.rows.filter((r) => r.owned).length - 1;
  const ending = row.id === props.terminus;
  return (
    <div className="cw-order-tools">
      <IconButton
        icon="arrowUp"
        label="Move up"
        disabled={index === 0}
        onClick={() => props.onMove(index, index - 1)}
      />
      <IconButton
        icon="arrowDown"
        label="Move down"
        disabled={index === last}
        onClick={() => props.onMove(index, index + 1)}
      />
      {props.onInsertAfter ? (
        <IconButton
          icon="plus"
          label="Insert a scene after this one"
          onClick={() => props.onInsertAfter?.(index)}
        />
      ) : null}
      {props.onEditScene ? (
        <IconButton
          icon="edit"
          label="Edit this scene"
          onClick={() => props.onEditScene?.(row.id)}
        />
      ) : null}
      {props.onMakeEnding ? (
        <IconButton
          icon="flag"
          label={ending ? "Already the book's ending" : "Make this the book's ending"}
          disabled={ending}
          onClick={() => props.onMakeEnding?.(row)}
        />
      ) : null}
      <IconButton
        icon="x"
        label="Remove from this thread"
        onClick={() => props.onRemove(index)}
      />
    </div>
  );
}

export function SceneOrder(props: SceneOrderProps) {
  const list = useRef<HTMLOListElement>(null);
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dropAt, setDropAt] = useState<{ index: number; below: boolean } | null>(null);
  // The scene a keyboard move is about to redraw, focused again once it has
  // been: a run of presses walks it along. Taken once, so focus is never
  // pulled back to the row from a field the writer moves on to.
  const refocus = useRef<string | null>(null);
  const owned = props.rows.filter((r) => r.owned).length;

  useEffect(() => {
    const scene = refocus.current;
    if (!scene) return;
    refocus.current = null;
    sceneElement(list.current, scene)?.focus();
  }, [props.rows]);

  const onKeyDown = (e: KeyboardEvent<HTMLLIElement>, row: OrderRow) => {
    if (e.target !== e.currentTarget || row.index === null) return;
    const to = keyMove(e.key, row.index, owned);
    if (to !== null) {
      e.preventDefault();
      refocus.current = row.id;
      props.onMove(row.index, to);
    } else if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      props.onRemove(row.index);
    }
  };

  const dragHandlers = (row: OrderRow) => {
    const index = row.index;
    if (index === null) return {};
    return {
      draggable: true,
      onDragStart: (e: DragEvent<HTMLLIElement>) => {
        setDragFrom(index);
        e.dataTransfer.effectAllowed = "move";
        // Firefox will not start a drag without data on the transfer.
        e.dataTransfer.setData("text/plain", row.id);
      },
      onDragEnd: () => {
        setDragFrom(null);
        setDropAt(null);
      },
      onDragOver: (e: DragEvent<HTMLLIElement>) => {
        if (dragFrom === null || dragFrom === index) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setDropAt({ index, below: isBelowMidpoint(e) });
      },
      onDrop: (e: DragEvent<HTMLLIElement>) => {
        e.preventDefault();
        if (dragFrom !== null && dragFrom !== index)
          props.onMove(dragFrom, dropIndex(dragFrom, index, isBelowMidpoint(e)));
        setDragFrom(null);
        setDropAt(null);
      },
    };
  };

  if (!props.rows.length) {
    return <p className="cw-order-empty">No scenes yet — add the first one to begin.</p>;
  }
  return (
    <ol ref={list} className="cw-order" aria-label={props.label}>
      {props.rows.map((row) => {
        const marker = markerOf(row.scene);
        const drop =
          dropAt && row.index === dropAt.index
            ? dropAt.below
              ? " is-drop-after"
              : " is-drop-before"
            : "";
        const classes = `cw-order-row${row.owned ? "" : " is-inherited"}${marker ? ` has-${marker}` : ""}${
          dragFrom !== null && row.index === dragFrom ? " is-dragging" : ""
        }${props.moved?.has(row.id) ? " is-moved" : ""}${drop}`;
        return (
          <li
            key={`${row.id}-${row.index ?? "inherited"}`}
            className={classes}
            data-event={row.id}
            tabIndex={row.owned ? 0 : undefined}
            aria-label={
              row.owned
                ? `${row.title}, scene ${(row.index ?? 0) + 1} of ${owned}`
                : `${row.title}, inherited`
            }
            onKeyDown={(e) => onKeyDown(e, row)}
            {...dragHandlers(row)}
          >
            <span
              className="cw-order-handle"
              aria-hidden="true"
              title={
                row.owned ? "Drag to reorder" : "Inherited — edit it on its own thread"
              }
            >
              <Icon name={row.owned ? "grip" : "shield"} size={15} />
            </span>
            <div className="cw-order-main">
              <div className="cw-order-head">
                <span className="cw-order-when">{row.when}</span>
                <span className="cw-order-title">{row.title}</span>
                {row.id === props.terminus ? <Badge tone="warn">Ending</Badge> : null}
                {row.owned ? null : (
                  <Badge>from {props.continuationTitle ?? "its continuation"}</Badge>
                )}
              </div>
              <FindingList book={props.book} scene={row.scene} onJump={props.onJump} />
            </div>
            {row.owned ? <RowTools row={row} props={props} /> : null}
          </li>
        );
      })}
    </ol>
  );
}
