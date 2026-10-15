// Draws the dependency diagram from `logic/goals/layout`'s coordinates.
//
// Edges in one SVG layer, boxes as positioned HTML on top: SVG text neither
// wraps nor clips, so a long goal name would run over the box beside it, while
// HTML text is clipped by its box at any size and in either theme's font.
//
// Direction is the whole message: an edge runs from a prerequisite *down* to
// the goal that needs it. Selecting a goal keeps it, everything it rests on
// and everything resting on it bright, and lets the rest of the book recede;
// hovering a box lights the edges that touch it.

import { useMemo, useState } from "react";
import type { Goal } from "../../api/types";
import { layoutGoals, type GoalEdge } from "../../logic/goals/layout";
import {
  boxSubtitle,
  boxWhen,
  edgeOnChain,
  inFocus,
  lineage,
  type Lineage,
} from "../../logic/goals/goals";
import { useTextScale } from "./useTextScale";

function edgeClass(
  edge: GoalEdge,
  selected: string | null,
  chain: Lineage | null,
  hovered: string | null,
) {
  const lit = selected && chain ? edgeOnChain(edge, selected, chain) : false;
  const touched = hovered !== null && (edge.from === hovered || edge.to === hovered);
  const dim = selected !== null && !lit;
  return `cw-goal-edge${lit ? " is-lit" : ""}${touched ? " is-touched" : ""}${dim ? " is-dim" : ""}`;
}

function GoalBox({
  goal,
  style,
  selected,
  dim,
  onPick,
  onHover,
}: {
  goal: Goal;
  style: { left: number; top: number; width: number; height: number };
  selected: boolean;
  dim: boolean;
  onPick: (id: string) => void;
  onHover: (id: string | null) => void;
}) {
  const subtitle = boxSubtitle(goal);
  const when = boxWhen(goal);
  return (
    <button
      type="button"
      className={`cw-goal-node is-${goal.status.state}${selected ? " is-selected" : ""}${dim ? " is-dim" : ""}`}
      style={style}
      title={goal.title}
      aria-pressed={selected}
      aria-label={`${goal.title}: ${subtitle}${when ? `, ${when}` : ""}`}
      onClick={() => onPick(goal.id)}
      onMouseEnter={() => onHover(goal.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(goal.id)}
      onBlur={() => onHover(null)}
    >
      <span className="cw-goal-node-label">{goal.title}</span>
      <span className="cw-goal-node-sub">{subtitle}</span>
      <span className="cw-goal-node-when">{when}</span>
    </button>
  );
}

export function GoalDiagram({
  goals,
  selected,
  onPick,
}: {
  goals: Goal[];
  selected: string | null;
  onPick: (id: string) => void;
}) {
  const scale = useTextScale();
  const [hovered, setHovered] = useState<string | null>(null);
  const layout = useMemo(() => layoutGoals(goals, { scale }), [goals, scale]);
  const byId = useMemo(() => new Map(goals.map((g) => [g.id, g])), [goals]);
  const known = selected !== null && byId.has(selected) ? selected : null;
  const chain = useMemo(() => (known ? lineage(goals, known) : null), [goals, known]);
  const { width, height } = layout;
  return (
    <div className="cw-goal-diagram">
      <div
        className={`cw-goal-canvas${known ? " has-selection" : ""}`}
        style={{ width, height }}
        role="group"
        aria-label="Goal dependencies, prerequisites above the goals that need them"
      >
        <svg
          className="cw-goal-edges"
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          aria-hidden="true"
        >
          {layout.edges.map((edge) => {
            const classes = edgeClass(edge, known, chain, hovered);
            return (
              <g key={`${edge.from}->${edge.to}`} className={classes}>
                <path className="cw-goal-edge-line" d={edge.path} />
                <polygon className="cw-goal-edge-head" points={edge.arrow} />
              </g>
            );
          })}
        </svg>
        {layout.nodes.map((node) => {
          const goal = byId.get(node.id);
          if (!goal) return null;
          return (
            <GoalBox
              key={node.id}
              goal={goal}
              style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
              selected={node.id === known}
              dim={!inFocus(node.id, known, chain)}
              onPick={onPick}
              onHover={setHovered}
            />
          );
        })}
      </div>
    </div>
  );
}
