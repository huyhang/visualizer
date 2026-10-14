import type { Job } from "../../api/types";
import { STAGES, stageStates, waitingLine } from "../../logic/progress";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";

/** The researcher at work: which stage it is in, and what it says it is doing. */
export function JobProgress({
  job,
  onCancel,
  cancelling,
}: {
  job: Job;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const states = stageStates(job);
  const waiting = waitingLine(job);
  return (
    <div className="st-progress-card">
      <div className="st-progress-orb" aria-hidden="true">
        <span />
      </div>
      <p className="st-progress-now" aria-live="polite">
        {waiting ?? job.progress?.message ?? "Working…"}
      </p>
      <ol className="st-stages">
        {STAGES.map((stage, n) => (
          <li
            key={stage.key}
            className={`st-stage is-${states[n]}`}
            aria-current={states[n] === "current" ? "step" : undefined}
          >
            <span className="st-stage-mark">
              {states[n] === "done" ? <Icon name="check" size={12} /> : null}
            </span>
            {stage.label}
          </li>
        ))}
      </ol>
      <p className="st-muted st-small">
        Research usually takes a few minutes. You can keep reading other topics; this one
        updates on its own.
      </p>
      <Button variant="ghost" size="sm" icon="stop" onClick={onCancel} busy={cancelling}>
        Stop researching
      </Button>
    </div>
  );
}
