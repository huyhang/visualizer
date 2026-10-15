// One goal in the list under the diagram. Closed, a single row; open,
// everything the book knows about it.
//
// Open *is* selected, and selected is the URL, so the diagram and the list are
// one control rather than two kept in step, and a link to a goal still means
// what it always meant. Opening one scrolls it into view when it is off
// screen -- a writer who clicked a card open is already looking at it.

import { useEffect, useRef, useState } from "react";
import type { Goal, GoalRef } from "../../api/types";
import { useRoute } from "../../hooks/useRoute";
import { useThreads } from "../../hooks/useThreads";
import { STATE_WORDS, summaryLine, whenLine } from "../../logic/goals/goals";
import { to } from "../../logic/route";
import { Chip, GoalChip, ThreadChip } from "../../components/common/Chips";
import { useActions } from "../../components/shell/Actions";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { DeleteGoalDialog } from "../../editors/goal/DeleteGoalDialog";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";

const TONES = { achieved: "ok", open: "neutral", conflicted: "danger" } as const;

/** Whether an element's top edge is somewhere the reader can already see. */
function inView(node: HTMLElement): boolean {
  const box = node.getBoundingClientRect();
  return box.top >= 0 && box.top <= (window.innerHeight || 0);
}

function GoalRefs({
  refs,
  empty,
  onGoal,
}: {
  refs: GoalRef[];
  empty: string;
  onGoal: (id: string) => void;
}) {
  if (!refs.length) return <span className="cw-muted">{empty}</span>;
  return (
    <div className="cw-chip-row">
      {refs.map((r) => (
        <GoalChip key={r.id} goal={r} onOpen={r.missing ? undefined : onGoal} />
      ))}
    </div>
  );
}

function GoalFacts({ goal, onGoal }: { goal: Goal; onGoal: (id: string) => void }) {
  const { id: book } = useBookScope();
  const { get } = useThreads(book);
  const { go } = useRoute();
  const inspector = useInspector();
  const when = whenLine(goal);
  return (
    <dl className="cw-facts cw-goal-facts">
      <div className="cw-fact">
        <dt>Rests on</dt>
        <dd>
          <GoalRefs refs={goal.dependencies} empty="Nothing." onGoal={onGoal} />
        </dd>
      </div>
      <div className="cw-fact">
        <dt>Needed by</dt>
        <dd>
          <GoalRefs refs={goal.required_by} empty="Nothing yet." onGoal={onGoal} />
        </dd>
      </div>
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
            <span className="cw-muted">No thread yet.</span>
          )}
        </dd>
      </div>
      <div className="cw-fact">
        <dt>Achieved at</dt>
        <dd>
          {when && goal.achieved_at ? (
            <Chip
              tone="ok"
              icon="check"
              title="Open this scene"
              onClick={() => inspector.open({ kind: "scene", id: goal.achieved_at ?? "" })}
            >
              {when}
            </Chip>
          ) : (
            <span className="cw-muted">No scene yet.</span>
          )}
        </dd>
      </div>
    </dl>
  );
}

function CardBody({ goal, onGoal }: { goal: Goal; onGoal: (id: string) => void }) {
  return (
    <div className="cw-goal-card-body">
      {goal.description ? <p className="cw-goal-description">{goal.description}</p> : null}
      <GoalFacts goal={goal} onGoal={onGoal} />
      {goal.status.findings.length ? (
        <ul className="cw-findings">
          {goal.status.findings.map((f, n) => (
            <li key={n} className={`cw-finding is-${f.severity}`}>
              {f.message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function WriterActions({ goal, onDeleted }: { goal: Goal; onDeleted: () => void }) {
  const { editGoal } = useActions();
  const [deleting, setDeleting] = useState(false);
  const { id: book } = useBookScope();
  return (
    <div className="cw-goal-card-actions">
      {editGoal ? (
        <Button size="sm" icon="edit" onClick={() => editGoal(goal.id)}>
          Edit
        </Button>
      ) : null}
      <Button size="sm" variant="ghost" icon="trash" onClick={() => setDeleting(true)}>
        Delete
      </Button>
      <DeleteGoalDialog
        book={book}
        goal={goal}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={onDeleted}
      />
    </div>
  );
}

export function GoalCard({ goal, open }: { goal: Goal; open: boolean }) {
  const { id: book, canWrite } = useBookScope();
  const { go } = useRoute();
  const ref = useRef<HTMLElement>(null);
  const select = (id: string | null) => go(to.goals(book, id));
  useEffect(() => {
    if (open && ref.current && !inView(ref.current))
      ref.current.scrollIntoView?.({ block: "center", behavior: "smooth" });
  }, [open]);
  const state = goal.status.state;
  return (
    <article
      ref={ref}
      id={`goal-${goal.id}`}
      className={`cw-goal-card is-${state}${open ? " is-expanded" : ""}`}
    >
      <div className="cw-goal-card-head">
        <button
          type="button"
          className="cw-goal-card-toggle"
          aria-expanded={open}
          onClick={() => select(open ? null : goal.id)}
        >
          <Icon name={open ? "chevronDown" : "chevronRight"} size={15} />
          <span className="cw-goal-card-title">{goal.title}</span>
          <Badge tone={TONES[state]}>
            {state === "achieved" ? `✓ ${STATE_WORDS[state]}` : STATE_WORDS[state]}
          </Badge>
          <span className="cw-goal-card-summary">{summaryLine(goal)}</span>
        </button>
        {open && canWrite ? (
          <WriterActions goal={goal} onDeleted={() => select(null)} />
        ) : null}
      </div>
      {open ? <CardBody goal={goal} onGoal={(id) => select(id)} /> : null}
    </article>
  );
}
