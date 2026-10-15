// The text half of the map: period headings, and a row per slot -- a scene, a
// folded stretch of one thread's solitary scenes, or several scenes happening
// at once. Each row marks its line with `data-anchor` so the drawing beside it
// can find it (see useAnchors).
//
// A row's title opens the scene beside the map; its twisty opens it in place.
// Escape closes a scene opened in place without reaching for the mouse.

import { createContext, useContext, type KeyboardEvent, type ReactNode } from "react";
import type { GoalRef } from "../../api/types";
import type { Entry, Slot } from "../../logic/map/grouping";
import type { LaidNode } from "../../logic/map/layout";
import { plural } from "../../logic/text";
import { Chip, GoalChip } from "../../components/common/Chips";
import { Icon } from "../../../components/ui/Icon";
import { SceneDetails } from "./SceneDetails";
import { ThreadSwatch } from "./ThreadPicker";

/** Two marks before the rest fold away: a map row is a line in a dense list. */
export const MARKS_ON_A_ROW = 2;

export interface RowControls {
  isOpen: (id: string) => boolean;
  toggleScene: (id: string) => void;
  unfold: (bandId: string) => void;
  toggleMoment: (slotId: string) => void;
  marksOpen: (id: string) => boolean;
  toggleMarks: (id: string) => void;
  inspectScene: (id: string) => void;
  openGoal: (id: string) => void;
  /** The goals landing on each drawn node; empty when marks are off. */
  goalsAt: Map<string, GoalRef[]>;
  focusEvent: string | null;
  /** Whether the lens fades this node. */
  fades: (node: LaidNode) => boolean;
  /** The first thread through a node, to open it on. */
  homeThread: (id: string) => string | null;
  /** Light up the threads through a node, or none. */
  hover: (id: string | null) => void;
}

const RowContext = createContext<RowControls | null>(null);

export function RowControlsProvider({
  value,
  children,
}: {
  value: RowControls;
  children: ReactNode;
}) {
  return <RowContext.Provider value={value}>{children}</RowContext.Provider>;
}

function useRows(): RowControls {
  const value = useContext(RowContext);
  if (!value) throw new Error("Map rows need a <RowControlsProvider>.");
  return value;
}

function Twisty({
  open,
  label,
  onClick,
}: {
  open: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="cw-map-twisty"
      aria-expanded={open}
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      <Icon name={open ? "chevronDown" : "chevronRight"} size={14} />
    </button>
  );
}

function GoalMarks({ id }: { id: string }) {
  const rows = useRows();
  const goals = rows.goalsAt.get(id) ?? [];
  if (!goals.length) return null;
  const open = rows.marksOpen(id);
  const shown = open ? goals : goals.slice(0, MARKS_ON_A_ROW);
  const more = goals.length - MARKS_ON_A_ROW;
  return (
    <div className="cw-map-marks">
      {shown.map((g) => (
        <GoalChip key={g.id} goal={g} onOpen={rows.openGoal} />
      ))}
      {more > 0 ? (
        <Chip
          tone="muted"
          onClick={() => rows.toggleMarks(id)}
          title={open ? "Fold these goals away" : "Show every goal delivered here"}
        >
          {open ? "fewer" : `+${more} more`}
        </Chip>
      ) : null}
    </div>
  );
}

function Title({ node }: { node: LaidNode }) {
  const rows = useRows();
  return (
    <button
      type="button"
      className={`cw-map-title${node.isTerminus ? " is-terminus" : ""}`}
      title={
        node.isTerminus
          ? "The book's ending — every thread ends here"
          : "Open this scene beside the map"
      }
      onClick={() => rows.inspectScene(node.id)}
    >
      {node.title}
    </button>
  );
}

/** Escape closes a scene opened in place; only when it is open, so the key stays free otherwise. */
function closeOnEscape(open: boolean, close: () => void) {
  return (e: KeyboardEvent) => {
    if (e.key !== "Escape" || !open) return;
    e.stopPropagation();
    close();
  };
}

/** One scene's line, its marks and, opened, its details. */
function Scene({ node, when, anchor }: { node: LaidNode; when?: string; anchor?: string }) {
  const rows = useRows();
  const open = rows.isOpen(node.id);
  const classes = [
    "cw-map-scene",
    open && "is-open",
    node.id === rows.focusEvent && "is-focused",
    rows.fades(node) && "cw-faded",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div
      className={classes}
      data-scene={node.id}
      onKeyDown={closeOnEscape(open, () => rows.toggleScene(node.id))}
      onMouseEnter={() => rows.hover(node.id)}
      onMouseLeave={() => rows.hover(null)}
    >
      <div className="cw-map-line" data-anchor={anchor}>
        <Twisty
          open={open}
          label={open ? "Close this scene" : "Show this scene in full"}
          onClick={() => rows.toggleScene(node.id)}
        />
        <ThreadSwatch color={node.color} dash={node.dash} className="cw-map-lane-dot" />
        <Title node={node} />
        {when ? <span className="cw-map-when">{when}</span> : null}
      </div>
      <GoalMarks id={node.id} />
      {open ? <SceneDetails id={node.id} thread={rows.homeThread(node.id)} /> : null}
    </div>
  );
}

/** A folded stretch: an amount of story, unfolding into its scenes. */
function Band({ node, when, anchor }: { node: LaidNode; when?: string; anchor?: string }) {
  const rows = useRows();
  const count = node.events?.length ?? 0;
  return (
    <div
      className={`cw-map-scene is-band${rows.fades(node) ? " cw-faded" : ""}`}
      data-scene={node.id}
    >
      <div className="cw-map-line" data-anchor={anchor}>
        <button
          type="button"
          className="cw-map-band"
          title={`Unfold these ${count} scenes`}
          onClick={() => rows.unfold(node.id)}
        >
          <Icon name="chevronRight" size={14} />
          <ThreadSwatch
            color={node.color}
            dash={node.dash}
            className="cw-map-lane-dot"
            hollow
          />
          <span className="cw-map-band-title">{node.title}</span>
        </button>
        {when ? <span className="cw-map-when">{when}</span> : null}
      </div>
      <GoalMarks id={node.id} />
    </div>
  );
}

function SlotNode({
  node,
  when,
  anchor,
}: {
  node: LaidNode;
  when?: string;
  anchor?: string;
}) {
  return node.isBand ? (
    <Band node={node} when={when} anchor={anchor} />
  ) : (
    <Scene node={node} when={when} anchor={anchor} />
  );
}

/** Several scenes at one moment, sharing one line so nothing implies an order the story has not got. */
function Moment({ slot }: { slot: Slot }) {
  const rows = useRows();
  const open = !slot.collapsed;
  const count = slot.count ?? slot.nodes.length;
  return (
    <div className={`cw-map-row is-moment${open ? "" : " is-closed"}`}>
      <div className="cw-map-line cw-map-moment-bar" data-anchor={slot.id}>
        <Twisty
          open={open}
          label={
            open
              ? `Hide the ${count} scenes at this moment`
              : `Show the ${count} scenes at this moment`
          }
          onClick={() => rows.toggleMoment(slot.id)}
        />
        <span className="cw-map-moment-count">{count} at once</span>
        {slot.when ? <span className="cw-map-when">{slot.when}</span> : null}
      </div>
      {open ? (
        <div className="cw-map-moment-scenes">
          {slot.nodes.map((n) => (
            <SlotNode key={n.id} node={n} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Row({ slot }: { slot: Slot }) {
  if (slot.isGroup) return <Moment slot={slot} />;
  const node = slot.nodes[0];
  if (!node) return null;
  return (
    <div className="cw-map-row">
      <SlotNode node={node} when={slot.when} anchor={slot.id} />
    </div>
  );
}

export function MapRows({ sequence }: { sequence: Entry[] }) {
  return (
    <>
      {sequence.map((entry) =>
        entry.kind === "header" ? (
          <div
            key={`h:${entry.header.level}:${entry.header.label}:${entry.header.y}`}
            className={`cw-map-period is-level-${Math.min(entry.header.level, 2)}`}
            role="heading"
            aria-level={3 + Math.min(entry.header.level, 2)}
          >
            {entry.header.label}
          </div>
        ) : (
          <Row key={entry.row.id} slot={entry.row} />
        ),
      )}
    </>
  );
}

/** "Following Sir Aldric — 3 of 6 scenes", worded for the rows on screen. */
export function sceneCount(shown: number, total: number): string {
  return `${shown} of ${plural(total, "scene")}`;
}
