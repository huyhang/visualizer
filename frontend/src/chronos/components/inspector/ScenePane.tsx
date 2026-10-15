// One scene in full, beside whatever you were reading: when and where it
// happens, who and what is in it, which threads pass through it and which
// goals it delivers. Its cast opens in the same panel, and Back returns here.

import type { Graph, SceneEvent } from "../../api/types";
import { useEvent } from "../../hooks/queries";
import { useThreads } from "../../hooks/useThreads";
import { timeframe } from "../../logic/text";
import { ArticleChip, Chip, GoalChip, ThreadChip } from "../common/Chips";
import { QueryState } from "../common/QueryState";
import { useActions } from "../shell/Actions";
import { useBookScope } from "../shell/BookScope";
import { useInspector } from "../shell/InspectorContext";
import { useRoute } from "../../hooks/useRoute";
import { to } from "../../logic/route";
import { Button } from "../../../components/ui/Button";

/** The threads whose path passes through `scene`, in the book's order. */
export function threadsThrough(graph: Graph | undefined, scene: string): string[] {
  return (graph?.plotlines ?? [])
    .filter((p) => p.effective_events.includes(scene))
    .map((p) => p.id);
}

/** The goals `scene` delivers. */
export function goalsDeliveredAt(graph: Graph | undefined, scene: string) {
  return (graph?.goals ?? []).filter((g) => g.achieved_at === scene);
}

function Roles({ scene, graph }: { scene: SceneEvent; graph: Graph | undefined }) {
  const roles: string[] = [];
  if (graph?.terminus === scene.id) roles.push("The book's ending");
  if (graph?.convergence.includes(scene.id)) roles.push("Threads join here");
  if (graph?.divergence.includes(scene.id)) roles.push("A thread departs here");
  if (!roles.length) return null;
  return (
    <div className="cw-chip-row">
      {roles.map((r) => (
        <Chip key={r} tone="accent" icon="branch">
          {r}
        </Chip>
      ))}
    </div>
  );
}

function SceneBody({ scene }: { scene: SceneEvent }) {
  const { id: book, canWrite } = useBookScope();
  const { graph, get } = useThreads(book);
  const inspector = useInspector();
  const { go } = useRoute();
  const actions = useActions();
  const openArticle = (ref: SceneEvent["location"]) =>
    inspector.push({ kind: "article", ref });
  const threads = threadsThrough(graph, scene.id);
  const goals = goalsDeliveredAt(graph, scene.id);
  const window = scene.window;
  return (
    <div className="cw-pane">
      <div className="cw-pane-kicker">Scene</div>
      <h2 className="cw-pane-title">{scene.title || scene.id}</h2>
      <p className="cw-pane-when">{timeframe(scene)}</p>
      {!scene.scheduled && window && (window.earliest_label || window.latest_label) ? (
        <p className="cw-muted cw-small">
          Could happen between {window.earliest_label ?? "the beginning"} and{" "}
          {window.latest_label ?? "the end"}.
        </p>
      ) : null}
      <Roles scene={scene} graph={graph} />
      <dl className="cw-facts">
        <div className="cw-fact">
          <dt>Where</dt>
          <dd>
            <ArticleChip book={book} entity={scene.location} onOpen={openArticle} />
          </dd>
        </div>
        {scene.characters?.length ? (
          <div className="cw-fact">
            <dt>Who</dt>
            <dd className="cw-chip-row">
              {scene.characters.map((c) => (
                <ArticleChip key={c.id} book={book} entity={c} onOpen={openArticle} />
              ))}
            </dd>
          </div>
        ) : null}
        {scene.items?.length ? (
          <div className="cw-fact">
            <dt>What</dt>
            <dd className="cw-chip-row">
              {scene.items.map((c) => (
                <ArticleChip key={c.id} book={book} entity={c} onOpen={openArticle} />
              ))}
            </dd>
          </div>
        ) : null}
        {threads.length ? (
          <div className="cw-fact">
            <dt>Threads</dt>
            <dd className="cw-chip-row">
              {threads.map((t) => (
                <ThreadChip
                  key={t}
                  id={t}
                  thread={get(t)}
                  onOpen={(id) => go(to.plotline(book, id, scene.id))}
                />
              ))}
            </dd>
          </div>
        ) : null}
        {goals.length ? (
          <div className="cw-fact">
            <dt>Delivers</dt>
            <dd className="cw-chip-row">
              {goals.map((g) => (
                <GoalChip
                  key={g.id}
                  goal={g}
                  onOpen={(id) => inspector.push({ kind: "goal", id })}
                />
              ))}
            </dd>
          </div>
        ) : null}
      </dl>
      {scene.description ? (
        <div className="cw-prose">
          {scene.description.split(/\n{2,}/).map((p, n) => (
            <p key={n}>{p}</p>
          ))}
        </div>
      ) : null}
      {canWrite && actions.editScene ? (
        <div className="cw-pane-actions">
          <Button size="sm" icon="edit" onClick={() => actions.editScene?.(scene.id)}>
            Edit scene
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function ScenePane({ id }: { id: string }) {
  const { id: book, calendar } = useBookScope();
  const query = useEvent(book, id, calendar);
  return <QueryState query={query}>{(scene) => <SceneBody scene={scene} />}</QueryState>;
}
