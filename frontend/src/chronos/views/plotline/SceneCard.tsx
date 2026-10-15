// One scene on a thread's timeline: what it is called, where and with whom it
// happens, what it is in the weave, and the goals it pays off. Its title opens
// the scene in full beside the timeline; its cast opens there too.

import type { EntityRef, EventSummary, GoalRef } from "../../api/types";
import { useRoute } from "../../hooks/useRoute";
import { meetHints } from "../../logic/plotline/verdicts";
import { to } from "../../logic/route";
import { ArticleChip, Chip, GoalChip } from "../../components/common/Chips";
import { useActions } from "../../components/shell/Actions";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { Badge } from "../../../components/ui/Badge";
import { IconButton } from "../../../components/ui/Button";

function RoleBadge({ scene }: { scene: EventSummary }) {
  if (scene.is_terminus) return <Badge tone="warn">Ending</Badge>;
  if (scene.is_convergence) return <Badge tone="accent">Convergence</Badge>;
  if (scene.is_divergence) return <Badge tone="accent">Divergence</Badge>;
  return null;
}

function Cast({
  book,
  refs,
  onOpen,
}: {
  book: string;
  refs: EntityRef[];
  onOpen: (ref: EntityRef) => void;
}) {
  if (!refs.length) return null;
  return (
    <div className="cw-chip-row cw-pl-card-cast">
      {refs.map((r) => (
        <ArticleChip
          key={`${r.collection}/${r.id}`}
          book={book}
          entity={r}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
}

export function SceneCard({
  scene,
  plotline,
  goals,
  inheritedFrom,
}: {
  scene: EventSummary;
  plotline: string;
  goals: GoalRef[];
  /** The thread an inherited scene is stored on, when it is not this one. */
  inheritedFrom: string | null;
}) {
  const { id: book, canWrite } = useBookScope();
  const inspector = useInspector();
  const actions = useActions();
  const { go } = useRoute();
  const openArticle = (ref: EntityRef) => inspector.open({ kind: "article", ref });
  const hints = meetHints(scene);
  const cast = [...(scene.characters ?? []), ...(scene.items ?? [])];
  return (
    <article className="cw-pl-card">
      <header className="cw-pl-card-head">
        <button
          type="button"
          className="cw-pl-card-title"
          onClick={() => inspector.open({ kind: "scene", id: scene.id })}
        >
          {scene.title || scene.id}
        </button>
        <RoleBadge scene={scene} />
        {canWrite && actions.editScene ? (
          <IconButton
            icon="edit"
            label="Edit this scene"
            onClick={() => actions.editScene?.(scene.id)}
          />
        ) : null}
      </header>
      {scene.location ? (
        <div className="cw-pl-card-where">
          <span className="cw-muted">at</span>{" "}
          <ArticleChip book={book} entity={scene.location} onOpen={openArticle} />
        </div>
      ) : null}
      <Cast book={book} refs={cast} onOpen={openArticle} />
      {scene.description_preview ? (
        <p className="cw-pl-card-preview">{scene.description_preview}</p>
      ) : null}
      {hints.length || inheritedFrom || goals.length ? (
        <div className="cw-chip-row cw-pl-card-marks">
          {inheritedFrom ? (
            <Chip
              tone="muted"
              icon="branch"
              title="Stored on the thread this one continues into"
            >
              From {inheritedFrom}
            </Chip>
          ) : null}
          {hints.map((hint) => (
            <Chip
              key={hint}
              tone="accent"
              icon="branch"
              onClick={() => go(to.connected(book, plotline, scene.id))}
              title="See the threads that meet here"
            >
              {hint}
            </Chip>
          ))}
          {goals.map((g) => (
            <GoalChip
              key={g.id}
              goal={g}
              onOpen={(id) => inspector.open({ kind: "goal", id })}
            />
          ))}
        </div>
      ) : null}
    </article>
  );
}
