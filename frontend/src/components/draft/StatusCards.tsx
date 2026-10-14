import type { ArticleRef, Job, Query } from "../../api/types";
import { slugOf } from "../../logic/format";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { Icon } from "../ui/Icon";
import { PlanCard } from "./PlanCard";

/** A question the researcher could not answer, and a way to ask it again. */
export function FailedCard({
  job,
  onRetry,
  retrying,
  retryError,
}: {
  job: Job;
  onRetry: () => void;
  retrying: boolean;
  retryError: string | null;
}) {
  return (
    <div className="st-callout is-danger" role="alert">
      <Icon name="alert" size={18} />
      <div>
        <h3>This research didn't finish</h3>
        <p>{job.error?.message ?? "The research job failed."}</p>
        {retryError ? <p className="st-error-text">{retryError}</p> : null}
        <Button
          variant="secondary"
          size="sm"
          icon="sparkle"
          busy={retrying}
          onClick={onRetry}
        >
          Ask again
        </Button>
      </div>
    </div>
  );
}

/** A topic whose draft is gone from the inbox: where its material went. */
export function ClosedCard({
  job,
  world,
  articleUrl,
}: {
  job: Job;
  world: string;
  articleUrl: (ref: ArticleRef) => string;
}) {
  const notes = [
    ...job.notes,
    ...(job.accepted && !job.notes.includes(job.accepted) ? [job.accepted] : []),
  ];
  if (!notes.length) {
    return (
      <EmptyState icon="check" title="This draft is closed">
        Nothing from it was saved to a note.
      </EmptyState>
    );
  }
  return (
    <div className="st-callout is-ok">
      <Icon name="note" size={18} />
      <div>
        <h3>Saved to {notes.length === 1 ? "a note" : `${notes.length} notes`}</h3>
        <p>The draft is closed. What you kept lives on in your world:</p>
        <ul className="st-note-links">
          {notes.map((ref) => (
            <li key={ref}>
              <a
                href={articleUrl({ db: world, col: "research", id: slugOf(ref) })}
                target="_blank"
                rel="noreferrer"
              >
                {slugOf(ref)} <Icon name="external" size={12} />
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** Approving or cancelling a steer's search plan, in terms of the steer's job. */
export interface SteerPlanHandlers {
  approving: boolean;
  cancelling: boolean;
  onApprove: (job: Job, queries: Query[]) => void;
  onCancel: (job: Job) => void;
}

/**
 * A refinement of the draft being read. One asked with the plan check on
 * stops for its searches to be approved -- the box carries the draft's
 * settings over -- and is approved here, since a steer is not a topic of its
 * own; anything else is a banner.
 */
export function SteeringPanel({ job, plan }: { job: Job; plan: SteerPlanHandlers }) {
  if (job.state !== "awaiting_approval") return <SteeringBanner job={job} />;
  return (
    <PlanCard
      key={job.id}
      job={job}
      approving={plan.approving}
      cancelling={plan.cancelling}
      onApprove={(queries) => plan.onApprove(job, queries)}
      onCancel={() => plan.onCancel(job)}
    />
  );
}

/** A refinement under way (or one that failed) on the draft being read. */
function SteeringBanner({ job }: { job: Job }) {
  if (job.state === "failed") {
    return (
      <div className="st-banner is-danger">
        <Icon name="alert" size={14} /> Your last steer failed:{" "}
        {job.error?.message ?? "the job failed"}.
      </div>
    );
  }
  return (
    <div className="st-banner is-accent" aria-live="polite">
      <span className="st-spinner" style={{ width: 14, height: 14 }} aria-hidden="true" />
      Steering with your feedback — {job.progress?.message ?? "waiting for the GPU box"}.
      The new version will replace this one.
    </div>
  );
}
