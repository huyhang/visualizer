// One scene as the library shows it: its name, when, where and which threads
// pass through it, striped down its edge in those threads' colours. The same
// card hangs off the timeline's rail, sits in the undated shelf and opens out
// of a moment, so it carries its own thread colour rather than inheriting one.

import type { CSSProperties } from "react";
import type { EventRow } from "../../api/types";
import type { Threads } from "../../hooks/useThreads";
import { spanLabel } from "../../logic/timeaxis";
import { EntityName } from "../../components/common/EntityName";
import { Badge } from "../../../components/ui/Badge";
import { SceneTools, type SceneActions } from "./SceneTools";

/** The first of a scene's threads that has a colour: what its date, dot and border wear. */
export function sceneTint(plotlines: string[], threads: Threads): string | null {
  for (const id of plotlines) {
    const thread = threads.get(id);
    if (thread) return thread.color;
  }
  return null;
}

/** One band per thread, in that thread's hue *and* stroke: hue alone runs out at thirteen. */
function ThreadStripe({ plotlines, threads }: { plotlines: string[]; threads: Threads }) {
  const marks = plotlines.flatMap((id) => {
    const t = threads.get(id);
    return t ? [t] : [];
  });
  if (!marks.length) return null;
  return (
    <span className="cw-scene-stripe" aria-hidden="true">
      {marks.map((t) => (
        <span
          key={t.id}
          className={`cw-thread-mark stroke-${t.turn}`}
          style={{ "--thread": t.color } as CSSProperties}
        />
      ))}
    </span>
  );
}

/** The threads a scene is in, as named chips; "not in any thread" is worth seeing too. */
export function UsedBy({
  plotlines,
  threads,
  limit,
}: {
  plotlines: string[];
  threads: Threads;
  limit?: number;
}) {
  if (!plotlines.length)
    return <span className="cw-muted cw-scene-unused">not in any thread</span>;
  const shown = limit === undefined ? plotlines : plotlines.slice(0, limit);
  return (
    <span className="cw-scene-threads">
      {shown.map((id) => {
        const t = threads.get(id);
        return (
          <span
            key={id}
            className="cw-scene-thread"
            style={t ? ({ "--thread": t.color } as CSSProperties) : undefined}
          >
            {t?.title ?? id}
          </span>
        );
      })}
      {limit !== undefined && plotlines.length > limit ? (
        <span className="cw-scene-thread is-more">+{plotlines.length - limit}</span>
      ) : null}
    </span>
  );
}

export function Place({
  book,
  scene,
}: {
  book: string;
  scene: Pick<EventRow, "location" | "location_ref">;
}) {
  return (
    <span className="cw-muted">
      {scene.location_ref ? (
        <EntityName book={book} entity={scene.location_ref} />
      ) : (
        scene.location
      )}
    </span>
  );
}

export function SceneCard({
  book,
  scene,
  threads,
  terminus,
  faded,
  actions,
}: {
  book: string;
  scene: EventRow;
  threads: Threads;
  terminus: string | null | undefined;
  faded: boolean;
  actions: SceneActions;
}) {
  const tint = sceneTint(scene.plotlines, threads);
  return (
    <article
      className={`cw-scene-card${faded ? " cw-faded" : ""}`}
      style={tint ? ({ "--thread": tint } as CSSProperties) : undefined}
      data-scene={scene.id}
    >
      <ThreadStripe plotlines={scene.plotlines} threads={threads} />
      <div className="cw-scene-card-head">
        <button
          type="button"
          className="cw-scene-card-title"
          title="Open the whole scene"
          onClick={() => actions.open(scene.id)}
        >
          {scene.title}
        </button>
        {scene.id === terminus ? <Badge tone="warn">Ending</Badge> : null}
        <SceneTools scene={scene} actions={actions} />
      </div>
      {/* The year and month go first when the card is narrow: the axis says them. */}
      <div className="cw-scene-card-time" title={scene.when}>
        <span className="is-long">{spanLabel(scene) ?? scene.when}</span>
        <span className="is-short">{spanLabel(scene, true) ?? scene.when}</span>
      </div>
      <div className="cw-scene-card-meta">
        <Place book={book} scene={scene} />
        <UsedBy plotlines={scene.plotlines} threads={threads} limit={2} />
      </div>
    </article>
  );
}
