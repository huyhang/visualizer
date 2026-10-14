import { useState } from "react";
import type { Job, Query } from "../../api/types";
import { cleanQueries, MAX_QUERIES, planProblem } from "../../logic/plan";
import { timeAgo } from "../../logic/format";
import { Button, IconButton } from "../ui/Button";

/**
 * "Here's how I'll search": the box's plan, editable, waiting for a go-ahead.
 * A steer asked with the plan check on waits the same way, over its draft.
 */
export function PlanCard({
  job,
  approving,
  cancelling,
  onApprove,
  onCancel,
}: {
  job: Job;
  approving: boolean;
  cancelling: boolean;
  onApprove: (queries: Query[]) => void;
  onCancel: () => void;
}) {
  const [queries, setQueries] = useState<Query[]>(job.plan?.queries ?? []);
  const steer = !!job.refines;
  const problem = planProblem(queries, steer);
  const language = queries[0]?.language ?? "en";
  const update = (n: number, patch: Partial<Query>) =>
    setQueries(queries.map((q, i) => (i === n ? { ...q, ...patch } : q)));

  return (
    <div className="st-plan">
      <h3>{steer ? "Here's how I'll search again" : "Here's how I'll search"}</h3>
      <p className="st-muted">
        {steer ? "Your steer is waiting. " : "Nothing has been read yet. "}
        Edit, add or remove searches, then let the researcher go on.
        {job.plan?.expires_at
          ? ` This plan waits until ${new Date(job.plan.expires_at).toLocaleString()}.`
          : ""}
      </p>
      <ul className="st-plan-list">
        {queries.map((query, n) => (
          <li key={n} className="st-plan-query">
            <input
              className="st-input"
              value={query.q}
              onChange={(e) => update(n, { q: e.target.value })}
              aria-label={`Search ${n + 1}`}
              maxLength={200}
            />
            <input
              className="st-input st-plan-lang"
              value={query.language}
              onChange={(e) => update(n, { language: e.target.value })}
              aria-label={`Language of search ${n + 1}`}
              maxLength={5}
            />
            <IconButton
              icon="x"
              label={`Remove search ${n + 1}`}
              onClick={() => setQueries(queries.filter((_, i) => i !== n))}
            />
          </li>
        ))}
      </ul>
      {queries.length < MAX_QUERIES ? (
        <Button
          variant="ghost"
          size="sm"
          icon="plus"
          onClick={() => setQueries([...queries, { q: "", language }])}
        >
          Add a search
        </Button>
      ) : null}
      {problem ? <p className="st-error-text">{problem}</p> : null}
      <div className="st-plan-actions">
        <Button
          variant="primary"
          icon="send"
          busy={approving}
          disabled={!!problem}
          onClick={() => onApprove(cleanQueries(queries))}
        >
          Search with these
        </Button>
        <Button variant="ghost" busy={cancelling} onClick={onCancel}>
          {steer ? "Cancel the steer" : "Cancel the question"}
        </Button>
        <span className="st-muted st-small">Asked {timeAgo(job.created_at)}</span>
      </div>
    </div>
  );
}
