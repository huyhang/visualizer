// One goal in full, opened from a chip anywhere: what it is, whether a scene
// delivers it, what it rests on and what rests on it, and what is wrong with it.
// A prerequisite is a goal too, so following one stays in the panel.

import type { Goal } from "../../api/types";
import { useGoal } from "../../hooks/queries";
import { useRoute } from "../../hooks/useRoute";
import { useThreads } from "../../hooks/useThreads";
import { to } from "../../logic/route";
import { Chip, GoalChip, ThreadChip } from "../common/Chips";
import { QueryState } from "../common/QueryState";
import { useActions } from "../shell/Actions";
import { useBookScope } from "../shell/BookScope";
import { useInspector } from "../shell/InspectorContext";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";

export const GOAL_STATE = {
  achieved: { label: "Achieved", tone: "ok" },
  open: { label: "Open", tone: "neutral" },
  conflicted: { label: "Conflicted", tone: "danger" },
} as const;

function GoalBody({ goal }: { goal: Goal }) {
  const { id: book, canWrite } = useBookScope();
  const { get } = useThreads(book);
  const inspector = useInspector();
  const actions = useActions();
  const { go } = useRoute();
  const state = GOAL_STATE[goal.status.state];
  const openGoal = (id: string) => inspector.push({ kind: "goal", id });
  return (
    <div className="cw-pane">
      <div className="cw-pane-kicker">Goal</div>
      <h2 className="cw-pane-title">{goal.title}</h2>
      <div className="cw-chip-row">
        <Badge tone={state.tone}>{state.label}</Badge>
      </div>
      {goal.description ? <p className="cw-pane-lede">{goal.description}</p> : null}
      {goal.status.findings.length ? (
        <ul className="cw-findings">
          {goal.status.findings.map((f, n) => (
            <li key={n} className={`cw-finding is-${f.severity}`}>
              {f.message}
            </li>
          ))}
        </ul>
      ) : null}
      <dl className="cw-facts">
        <div className="cw-fact">
          <dt>Delivered</dt>
          <dd>
            {goal.achieved_scene ? (
              <Chip
                tone="ok"
                icon="check"
                onClick={() =>
                  inspector.push({ kind: "scene", id: goal.achieved_scene?.id ?? "" })
                }
              >
                {goal.achieved_scene.title}
              </Chip>
            ) : (
              <span className="cw-muted">No scene yet</span>
            )}
            {goal.achieved_scene?.when ? (
              <div className="cw-muted cw-small">{goal.achieved_scene.when}</div>
            ) : null}
          </dd>
        </div>
        {goal.dependencies.length ? (
          <div className="cw-fact">
            <dt>Rests on</dt>
            <dd className="cw-chip-row">
              {goal.dependencies.map((g) => (
                <GoalChip key={g.id} goal={g} onOpen={openGoal} />
              ))}
            </dd>
          </div>
        ) : null}
        {goal.required_by.length ? (
          <div className="cw-fact">
            <dt>Needed by</dt>
            <dd className="cw-chip-row">
              {goal.required_by.map((g) => (
                <GoalChip key={g.id} goal={g} onOpen={openGoal} />
              ))}
            </dd>
          </div>
        ) : null}
        <div className="cw-fact">
          <dt>Pursued by</dt>
          <dd className="cw-chip-row">
            {goal.plotlines.length ? (
              goal.plotlines.map((p) => (
                <ThreadChip
                  key={p.id}
                  id={p.id}
                  thread={get(p.id)}
                  onOpen={(id) => go(to.plotline(book, id))}
                />
              ))
            ) : (
              <span className="cw-muted">No thread yet</span>
            )}
          </dd>
        </div>
      </dl>
      <div className="cw-pane-actions">
        <Button size="sm" icon="target" onClick={() => go(to.goals(book, goal.id))}>
          Show among the goals
        </Button>
        {canWrite && actions.editGoal ? (
          <Button size="sm" icon="edit" onClick={() => actions.editGoal?.(goal.id)}>
            Edit goal
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function GoalPane({ id }: { id: string }) {
  const { id: book, calendar } = useBookScope();
  const query = useGoal(book, id, calendar);
  return <QueryState query={query}>{(goal) => <GoalBody goal={goal} />}</QueryState>;
}
