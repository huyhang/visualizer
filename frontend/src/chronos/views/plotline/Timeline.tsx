// A thread's scenes top to bottom in story order, on a rail. The book's own
// calendar decides the headings -- a Year/Month/Day calendar nests Year and
// Month above the scenes, with day and time beside each one -- so any invented
// calendar reads naturally with no per-calendar code here.

import type { CSSProperties } from "react";
import type { EventSummary, GoalRef } from "../../api/types";
import { markerOf, roleOf } from "../../logic/plotline/verdicts";
import { sections } from "../../logic/plotline/sections";
import { groupByPeriod } from "../../logic/timeaxis";
import { useLens } from "../../components/shell/Lens";
import { useBookScope } from "../../components/shell/BookScope";
import { FindingList } from "./Findings";
import { SceneCard } from "./SceneCard";

const INDENT_REM = 1;

export interface TimelineProps {
  events: EventSummary[];
  plotline: string;
  goalsAt: Map<string, GoalRef[]>;
  /** The scene the address asked for, highlighted on arrival. */
  focused: string | null;
  /** The name of the thread this one continues into, for inherited scenes. */
  continuationTitle: string | null;
  onJump: (scene: string) => void;
}

function Row({
  scene,
  label,
  props,
}: {
  scene: EventSummary;
  label: string;
  props: TimelineProps;
}) {
  const { id: book } = useBookScope();
  const lens = useLens();
  const marker = markerOf(scene);
  const role = roleOf(scene);
  const classes = [
    "cw-pl-row",
    props.focused === scene.id ? "is-focused" : "",
    lens.fades(scene.id) ? "cw-faded" : "",
  ];
  return (
    <li className={classes.filter(Boolean).join(" ")} data-event={scene.id}>
      <div className="cw-pl-time">{label}</div>
      <div className="cw-pl-rail" aria-hidden="true">
        <span
          className={`cw-pl-dot${role ? ` is-${role}` : ""}${marker ? ` has-${marker}` : ""}`}
        />
      </div>
      <div className="cw-pl-body">
        <FindingList book={book} scene={scene} onJump={props.onJump} />
        <SceneCard
          scene={scene}
          plotline={props.plotline}
          goals={props.goalsAt.get(scene.id) ?? []}
          inheritedFrom={scene.owned === false ? props.continuationTitle : null}
        />
      </div>
    </li>
  );
}

export function Timeline(props: TimelineProps) {
  return (
    <div className="cw-pl">
      {sections(groupByPeriod(props.events)).map((section, n) =>
        section.kind === "header" ? (
          <div
            key={`h${n}`}
            className={`cw-pl-head${section.level === 0 ? " is-top" : ""}`}
            style={{ "--cw-indent": `${section.level * INDENT_REM}rem` } as CSSProperties}
          >
            {section.label}
          </div>
        ) : (
          <ol
            key={`r${n}`}
            className="cw-pl-rows"
            style={{ "--cw-indent": `${section.depth * INDENT_REM}rem` } as CSSProperties}
          >
            {section.rows.map(({ event, label }) => (
              <Row key={event.id} scene={event} label={label} props={props} />
            ))}
          </ol>
        ),
      )}
    </div>
  );
}
