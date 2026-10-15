// The drawing: one SVG for the lanes, curves and dots, beside the rows that
// name them. The rows flow like any list; the SVG is drawn at the heights the
// rows actually landed at (useAnchors), so a dot always sits on its scene's
// line whatever the window width or text size.
//
// Hovering a thread -- its chip, or any scene on it -- lights up its whole
// path and quiets the rest.

import { useRef } from "react";
import type { MapModel } from "../../logic/map/grouping";
import type { LaidEdge, LaidNode } from "../../logic/map/layout";
import { geometry } from "../../logic/map/layout";
import { edgeShape } from "../../logic/map/edges";
import { useAnchors } from "./useAnchors";
import { MapRows } from "./MapRows";

const meets = (ids: Iterable<string>, hot: Set<string> | null) => {
  if (!hot) return false;
  for (const id of ids) if (hot.has(id)) return true;
  return false;
};

/** The y of each node: its slot's measured line, or the layout's estimate before anything is measured. */
export function nodeHeights(
  model: MapModel,
  centres: Map<string, number> | null,
): Map<string, number> {
  const out = new Map<string, number>();
  for (const slot of model.rows) {
    const y = centres?.get(slot.id) ?? slot.y;
    for (const n of slot.nodes) out.set(n.id, y);
  }
  return out;
}

function Edge({
  edge,
  y1,
  y2,
  hot,
}: {
  edge: LaidEdge;
  y1: number;
  y2: number;
  hot: Set<string> | null;
}) {
  const lit = meets(edge.plotlines, hot);
  const classes = [
    "cw-sg-edge",
    edge.isFocus && "is-focus",
    hot && (lit ? "is-hot" : "is-cold"),
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <path
      className={classes}
      d={edgeShape({ x1: edge.x1, y1, x2: edge.x2, y2 })}
      style={{ stroke: edge.color }}
      strokeDasharray={edge.dash || undefined}
    />
  );
}

function Dot({
  node,
  y,
  lit,
  cold,
  faded,
}: {
  node: LaidNode;
  y: number;
  lit: boolean;
  cold: boolean;
  faded: boolean;
}) {
  const r = geometry.NODE_R;
  const classes = ["cw-sg-node", lit && "is-hot", cold && "is-cold", faded && "is-faded"]
    .filter(Boolean)
    .join(" ");
  return (
    <g className={classes} data-node={node.id}>
      {node.isFocus && !node.isTerminus ? (
        <circle className="cw-sg-focus" cx={node.x} cy={y} r={r + 3.5} />
      ) : null}
      {node.isTerminus ? (
        <circle
          className="cw-sg-ring"
          cx={node.x}
          cy={y}
          r={r + 4}
          style={{ stroke: node.color }}
        />
      ) : null}
      {node.isBand ? (
        <circle
          className="cw-sg-dot is-band"
          cx={node.x}
          cy={y}
          r={r - 1}
          style={{ stroke: node.color }}
        />
      ) : (
        <circle
          className={`cw-sg-dot${node.isConvergence ? " is-merge" : ""}${node.isDivergence ? " is-split" : ""}`}
          cx={node.x}
          cy={y}
          r={r}
          style={{ fill: node.color }}
        />
      )}
    </g>
  );
}

export function StoryGraph({
  model,
  hot,
  threadsAt,
  fades,
}: {
  model: MapModel;
  /** The threads being hovered, or null. */
  hot: Set<string> | null;
  threadsAt: Map<string, Set<string>>;
  fades: (node: LaidNode) => boolean;
}) {
  const rows = useRef<HTMLDivElement>(null);
  const anchors = useAnchors(rows, model);
  const ys = nodeHeights(model, anchors?.centres ?? null);
  const height = anchors?.height ?? model.height;
  const yOf = (id: string) => ys.get(id) ?? 0;
  return (
    <div className="cw-sg-pane">
      <div
        className="cw-sg"
        style={{
          gridTemplateColumns: `${model.width}px minmax(0, 1fr)`,
          minWidth: model.minWidth,
        }}
      >
        <svg
          className={`cw-sg-svg${hot ? " has-hot" : ""}`}
          width={model.width}
          height={height}
          viewBox={`0 0 ${model.width} ${height}`}
          aria-hidden="true"
        >
          {model.edges.map((e) => (
            <Edge
              key={`${e.from}>${e.to}`}
              edge={e}
              y1={yOf(e.from)}
              y2={yOf(e.to)}
              hot={hot}
            />
          ))}
          {model.nodes.map((n) => {
            const lit = meets(threadsAt.get(n.id) ?? [], hot);
            return (
              <Dot
                key={n.id}
                node={n}
                y={yOf(n.id)}
                lit={lit}
                cold={Boolean(hot) && !lit}
                faded={fades(n)}
              />
            );
          })}
        </svg>
        <div className="cw-sg-rows" ref={rows}>
          <MapRows sequence={model.sequence} />
        </div>
      </div>
    </div>
  );
}
