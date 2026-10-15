// The map's controls: which threads are on it, and how it is drawn. A chip's
// swatch is the lane's own colour and stroke, so what you click is what you
// get -- and a thread that is off still shows its mark, which makes the picker
// the legend too.

import { useState } from "react";
import type { ThreadInfo } from "../../hooks/useThreads";
import { strokeClass } from "../../logic/map/edges";
import { matchesFilter } from "../../logic/map/selection";
import { SearchField } from "../../components/common/Fields";
import { Button } from "../../../components/ui/Button";

/** A thread's colour and stroke as one small mark: hollow and outlined once a stroke is in play. */
export function ThreadSwatch({
  color,
  dash,
  className = "cw-map-swatch",
  hollow = false,
}: {
  color: string;
  dash: string;
  className?: string;
  /** Drawn as a ring whatever the stroke: a folded stretch, not a scene. */
  hollow?: boolean;
}) {
  const stroke = strokeClass(dash);
  return (
    <span
      className={`${className}${stroke ? ` ${stroke}` : ""}`}
      style={stroke || hollow ? { borderColor: color } : { background: color }}
      aria-hidden="true"
    />
  );
}

function Toggle({
  on,
  onClick,
  children,
  title,
}: {
  on: boolean;
  onClick: () => void;
  children: string;
  title: string;
}) {
  return (
    <Button
      size="sm"
      variant={on ? "primary" : "secondary"}
      aria-pressed={on}
      title={title}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

export interface PickerProps {
  threads: ThreadInfo[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onAll: () => void;
  onNone: () => void;
  onInvert: () => void;
  compact: boolean;
  onCompact: () => void;
  showGoals: boolean;
  onGoals: () => void;
  /** Whether there are solo stretches to unfold, and whether they are. */
  canFold: boolean;
  unfolded: boolean;
  onFold: () => void;
  /** Hovering a chip lights its thread up on the drawing. */
  onHover: (id: string | null) => void;
}

export function ThreadPicker(props: PickerProps) {
  const { threads, selected, onToggle, onHover } = props;
  const [filter, setFilter] = useState("");
  const shown = threads.filter((t) => matchesFilter(t.title, filter));
  return (
    <div className="cw-map-picker">
      <div className="cw-map-controls">
        <SearchField
          value={filter}
          onChange={setFilter}
          placeholder="Filter threads…"
          label="Filter threads"
        />
        <div className="cw-map-buttons" role="group" aria-label="Choose threads">
          <Button size="sm" onClick={props.onAll} title="Show every thread">
            All
          </Button>
          <Button size="sm" onClick={props.onNone} title="Clear the selection">
            None
          </Button>
          <Button
            size="sm"
            onClick={props.onInvert}
            title="Swap which threads are shown for which are not"
          >
            Invert
          </Button>
        </div>
        <div className="cw-map-buttons" role="group" aria-label="How the map is drawn">
          <Toggle
            on={props.compact}
            onClick={props.onCompact}
            title="Tighter rows — more of the story on one screen"
          >
            Compact
          </Toggle>
          <Toggle
            on={!props.showGoals}
            onClick={props.onGoals}
            title="Show or hide where each goal lands"
          >
            Hide goals
          </Toggle>
          {props.canFold ? (
            <Toggle
              on={props.unfolded}
              onClick={props.onFold}
              title="Show every scene, including the stretches a thread walks alone"
            >
              Unfold all
            </Toggle>
          ) : null}
        </div>
      </div>
      <div className="cw-map-chips" role="group" aria-label="Threads on the map">
        {shown.map((t) => {
          const on = selected.has(t.id);
          return (
            <button
              key={t.id}
              type="button"
              className={`cw-map-pick${on ? " is-on" : ""}`}
              aria-pressed={on}
              title={on ? `Hide “${t.title}”` : `Show “${t.title}”`}
              onClick={() => onToggle(t.id)}
              onMouseEnter={() => onHover(on ? t.id : null)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(on ? t.id : null)}
              onBlur={() => onHover(null)}
            >
              <ThreadSwatch color={t.color} dash={t.dash} />
              <span>{t.title}</span>
            </button>
          );
        })}
        {shown.length === 0 ? (
          <span className="cw-muted cw-small">No threads match your filter.</span>
        ) : null}
      </div>
    </div>
  );
}
