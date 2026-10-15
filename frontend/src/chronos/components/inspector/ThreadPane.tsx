// One thread at a glance, without leaving the page you are on: its goals, its
// health and its scenes in order, with the way into its full timeline.

import type { EventSummary, Plotline } from "../../api/types";
import { usePlotline } from "../../hooks/queries";
import { useRoute } from "../../hooks/useRoute";
import { useThreads } from "../../hooks/useThreads";
import { to } from "../../logic/route";
import { plural, timeframe } from "../../logic/text";
import { GoalChip, ThreadDot } from "../common/Chips";
import { QueryState } from "../common/QueryState";
import { useBookScope } from "../shell/BookScope";
import { useInspector } from "../shell/InspectorContext";
import { Button } from "../../../components/ui/Button";

/** A thread's resolved path as summaries, whether or not it was expanded. */
export function pathOf(plotline: Plotline): EventSummary[] {
  return plotline.effective_events.map((e) => (typeof e === "string" ? { id: e } : e));
}

function ThreadBody({ plotline }: { plotline: Plotline }) {
  const { id: book } = useBookScope();
  const { get } = useThreads(book);
  const inspector = useInspector();
  const { go } = useRoute();
  const conflicts = plotline.status.conflicts ?? 0;
  return (
    <div className="cw-pane">
      <div className="cw-pane-kicker">
        <ThreadDot thread={get(plotline.id)} /> Thread
      </div>
      <h2 className="cw-pane-title">{plotline.title || plotline.id}</h2>
      <p className={conflicts ? "cw-problems" : "cw-muted"}>
        {conflicts ? plural(conflicts, "problem") : "No problems"}
      </p>
      {plotline.overview ? <p className="cw-pane-lede">{plotline.overview}</p> : null}
      {plotline.goal_refs?.length ? (
        <div className="cw-chip-row">
          {plotline.goal_refs.map((g) => (
            <GoalChip
              key={g.id}
              goal={g}
              onOpen={(id) => inspector.push({ kind: "goal", id })}
            />
          ))}
        </div>
      ) : null}
      <ol className="cw-mini-path">
        {pathOf(plotline).map((s) => (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => inspector.push({ kind: "scene", id: s.id })}
            >
              <span className="cw-mini-path-title">{s.title || s.id}</span>
              <span className="cw-mini-path-when">{timeframe(s)}</span>
            </button>
          </li>
        ))}
      </ol>
      <div className="cw-pane-actions">
        <Button size="sm" icon="branch" onClick={() => go(to.plotline(book, plotline.id))}>
          Open the thread
        </Button>
      </div>
    </div>
  );
}

export function ThreadPane({ id }: { id: string }) {
  const { id: book, calendar } = useBookScope();
  const query = usePlotline(book, id, calendar);
  return (
    <QueryState query={query}>
      {(plotline) => <ThreadBody plotline={plotline} />}
    </QueryState>
  );
}
