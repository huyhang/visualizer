// One issue in the Editor tab's list: what sort, the words it is about, and the
// first lines of what the editor said. Choosing it shows the words in the
// manuscript and opens the issue in full.

import type { ReviewIssue } from "../../api/types";
import {
  CHECK_LABELS,
  currentFix,
  isReplying,
  stanceOf,
  STANCE_LABELS,
} from "../../logic/review";

export function IssueRow({
  issue,
  placed,
  active,
  onChoose,
}: {
  issue: ReviewIssue;
  /** Whether its words are in the draft now; null when the issue is another draft's. */
  placed: boolean | null;
  active: boolean;
  onChoose: () => void;
}) {
  const stance = stanceOf(issue);
  const open = issue.status === "open";
  const fixable = Boolean(currentFix(issue).replacement) && placed === true && open;
  return (
    <li>
      <button
        type="button"
        className={`lw-issue-row lw-issue-${issue.check}${active ? " is-active" : ""}${issue.status !== "open" ? " is-done" : ""}`}
        aria-current={active || undefined}
        data-issue={issue.id}
        onClick={onChoose}
      >
        <span className="lw-issue-bar" aria-hidden="true" />
        <span className="lw-issue-main">
          <span className="lw-issue-top">
            <span className="lw-issue-kind">{CHECK_LABELS[issue.check]}</span>
            {issue.severity === "warning" ? (
              <span className="lw-issue-flag">Warning</span>
            ) : null}
            {fixable ? <span className="lw-issue-flag is-fix">Fix ready</span> : null}
            {placed === false && open ? (
              <span className="lw-issue-flag">Changed</span>
            ) : null}
            {isReplying(issue) ? (
              <span className="lw-issue-flag is-busy">Replying…</span>
            ) : null}
            {stance && !isReplying(issue) ? (
              <span className={`lw-issue-flag lw-stance-${stance}`}>
                {STANCE_LABELS[stance]}
              </span>
            ) : null}
          </span>
          <span className="lw-issue-quote">“{issue.quote}”</span>
          <span className="lw-issue-message">{issue.message}</span>
        </span>
      </button>
    </li>
  );
}
