// The Editor tab: ask the editor on the GPU box to read this draft, watch it
// work, then go through what it found -- in a list beside the page, or one
// issue at a time with its discussion.

import { Popover } from "radix-ui";
import { useState, type KeyboardEvent } from "react";
import type { SectionAddress } from "../../api/LogosApi";
import { LogosApiError, messageOf } from "../../api/errors";
import type { Check, ReviewIssue } from "../../api/types";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Spinner } from "../../../components/ui/Spinner";
import { StatusDot } from "../../../components/ui/StatusDot";
import type { Placement } from "../../editor/annotations";
import type { EditorReview } from "../../hooks/useEditorReview";
import { editorNote, noteReplacement, type NoteActions } from "../../logic/notes";
import {
  availabilityLabel,
  availabilityTone,
  CHECK_LABELS,
  CHECKS,
  editorAnnotationId,
  isActive,
  issueCounts,
  listedIssues,
  stageLabel,
  stepIssue,
  verificationLabel,
  type IssueFilter,
} from "../../logic/review";
import { LayerToggle } from "../tools/LayerToggle";
import { AskOptions, type AskSettings } from "./AskOptions";
import { Discussion } from "./Discussion";
import { IssueRow } from "./IssueRow";
import { NoteCard } from "./NoteCard";
import { ReviewHistory } from "./ReviewHistory";

function askError(error: unknown): string {
  if (error instanceof LogosApiError && error.isBusy) {
    return `The editor has as many reviews as it can take.${error.retryAfter ? ` Try again in ${error.retryAfter} seconds.` : ""}`;
  }
  return messageOf(error, "The review could not be started.");
}

export function EditorTab({
  review,
  at,
  draftId,
  settled,
  settings,
  onSettings,
  placement,
  blockOrder,
  selected,
  onSelect,
  actions,
  marked,
  onMarked,
}: {
  review: EditorReview;
  at: SectionAddress;
  draftId: string;
  settled: () => Promise<boolean>;
  settings: AskSettings;
  onSettings: (settings: AskSettings) => void;
  placement: Placement;
  blockOrder: string[];
  selected: string | null;
  onSelect: (issueId: string | null, show?: boolean) => void;
  actions: NoteActions;
  marked: boolean;
  onMarked: (marked: boolean) => void;
}) {
  const [filter, setFilter] = useState<IssueFilter>("open");
  const [checks, setChecks] = useState<Check[]>([...CHECKS]);
  const { availability, review: current } = review;
  const running = isActive(current?.state);
  const canAsk = Boolean(availability?.can_submit) && !running && !review.ask.isPending;
  const issues = current?.issues ?? [];
  const listed = listedIssues(issues, filter, checks, blockOrder, placement);
  const detail = issues.find((issue) => issue.id === selected) ?? null;
  const placed = (issue: ReviewIssue) => placement[editorAnnotationId(issue)] != null;

  const ask = () =>
    review.ask.mutate({
      checks: settings.checks,
      verify: settings.verify,
      dialect: settings.dialect,
      include: settings.include.map((item) => item.ref),
    });

  const onListKey = (event: KeyboardEvent) => {
    if (
      event.target instanceof HTMLTextAreaElement ||
      event.target instanceof HTMLInputElement
    )
      return;
    const key = event.key.toLowerCase();
    const step =
      key === "j" || key === "arrowdown" ? 1 : key === "k" || key === "arrowup" ? -1 : 0;
    if (step) {
      event.preventDefault();
      const next = stepIssue(listed, selected, step);
      if (next) onSelect(next.id, true);
      return;
    }
    const target = detail && current ? editorNote(detail, current.id) : null;
    if (!target) return;
    if (key === "a" && noteReplacement(target) && placed(detail!)) {
      event.preventDefault();
      actions.accept(target);
    } else if (key === "d") {
      event.preventDefault();
      actions.dismiss(target);
    }
  };

  return (
    <div className="lw-editor-tab" onKeyDown={onListKey}>
      <div className="lw-ask">
        <div className="lw-ask-status">
          <StatusDot
            tone={availabilityTone(availability?.state)}
            pulse={availability?.state === "cold"}
          />
          <span className="lw-ask-state">{availabilityLabel(availability)}</span>
          {availability?.model ? (
            <span className="lw-ask-model">{availability.model}</span>
          ) : null}
          <Popover.Root>
            <Popover.Trigger asChild>
              <button
                type="button"
                className="st-icon-btn lw-ask-settings"
                aria-label="Review settings"
                title="Review settings"
              >
                <Icon name="settings" />
              </button>
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content
                className="st-popover lw-options-popover"
                align="end"
                sideOffset={6}
                collisionPadding={12}
              >
                <AskOptions
                  at={at}
                  draft={draftId}
                  settings={settings}
                  onChange={onSettings}
                  settled={settled}
                />
                <Popover.Arrow className="st-popover-arrow" />
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
        </div>
        {availability && !availability.can_submit && availability.state !== "busy" ? (
          <p className="lw-muted lw-small">{availability.message}</p>
        ) : null}
        {running && current ? (
          <div className="lw-progress" role="status">
            <Spinner size={16} />
            <span>
              <strong>{stageLabel(current.state, current.progress)}…</strong>
              <small>
                The editor reads the saved draft. Keep writing; issues land where they
                belong.
              </small>
            </span>
            <Button
              size="sm"
              variant="ghost"
              busy={review.cancel.isPending}
              onClick={() => review.cancel.mutate(current.id)}
            >
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            variant="primary"
            icon="sparkle"
            className="lw-ask-button"
            disabled={!canAsk}
            busy={review.ask.isPending}
            onClick={ask}
          >
            {current ? "Ask for a fresh review" : "Ask the editor"}
          </Button>
        )}
        {review.ask.error ? (
          <p className="st-error-text">{askError(review.ask.error)}</p>
        ) : null}
        {issues.length ? (
          <LayerToggle
            label="Underline in the manuscript"
            checked={marked}
            onChange={onMarked}
          />
        ) : null}
      </div>

      {current?.state === "failed" ? (
        <div className="lw-callout is-danger">
          <Icon name="alert" />
          <span>{current.error?.message ?? "The review failed."}</span>
        </div>
      ) : null}

      {detail && current ? (
        <div className="lw-detail">
          <button type="button" className="lw-back-link" onClick={() => onSelect(null)}>
            <Icon name="arrowLeft" size={14} /> All issues
          </button>
          <NoteCard
            note={editorNote(detail, current.id)}
            actions={actions}
            placed={placed(detail)}
            references={current.references}
            variant="detail"
          >
            <Discussion
              key={detail.id}
              issue={detail}
              sending={review.discuss.isPending}
              error={review.discuss.error ? messageOf(review.discuss.error) : null}
              onSend={(text) =>
                review.discuss.mutate({ reviewId: current.id, issue: detail, text })
              }
            />
          </NoteCard>
        </div>
      ) : current?.state === "done" ? (
        <IssueList
          issues={issues}
          listed={listed}
          filter={filter}
          onFilter={setFilter}
          checks={checks}
          onChecks={setChecks}
          verification={verificationLabel(current)}
          outdated={current.outdated}
          selected={selected}
          placed={placed}
          onChoose={(issue) => onSelect(issue.id, true)}
        />
      ) : !current && !review.loading ? (
        <div className="lw-empty">
          <span className="lw-empty-icon">
            <Icon name="sparkle" size={20} />
          </span>
          <h3>A second reader for this draft</h3>
          <p>
            The editor checks continuity against your canon, anachronisms against verified
            research, and the prose itself. It runs on your own GPU box; nothing leaves your
            hardware.
          </p>
        </div>
      ) : null}

      <ReviewHistory
        reviews={review.reviews}
        viewing={review.viewing}
        onChoose={(id) => {
          onSelect(null);
          review.choose(id);
        }}
      />
    </div>
  );
}

function IssueList({
  issues,
  listed,
  filter,
  onFilter,
  checks,
  onChecks,
  verification,
  outdated,
  selected,
  placed,
  onChoose,
}: {
  issues: ReviewIssue[];
  listed: ReviewIssue[];
  filter: IssueFilter;
  onFilter: (filter: IssueFilter) => void;
  checks: Check[];
  onChecks: (checks: Check[]) => void;
  verification: string;
  outdated: boolean;
  selected: string | null;
  placed: (issue: ReviewIssue) => boolean;
  onChoose: (issue: ReviewIssue) => void;
}) {
  const counts = issueCounts(issues);
  if (!issues.length) {
    return (
      <div className="lw-empty is-clear">
        <span className="lw-empty-icon">
          <Icon name="check" size={20} />
        </span>
        <h3>Nothing to report</h3>
        <p>{verification || "The editor found no issues in this draft."}</p>
      </div>
    );
  }
  const present = CHECKS.filter((check) => issues.some((issue) => issue.check === check));
  return (
    <div className="lw-issues">
      <p className="lw-review-meta">
        <strong>{counts.open} open</strong> of {counts.total} · {verification}
      </p>
      {outdated ? (
        <div className="lw-callout">
          <Icon name="clock" />
          <span>
            This review read an earlier version of the draft. Issues show against the words
            as they are now.
          </span>
        </div>
      ) : null}
      <div className="lw-filters" role="group" aria-label="Show">
        {(["open", "done", "all"] as const).map((value) => (
          <button
            key={value}
            type="button"
            className={`lw-filter${filter === value ? " is-on" : ""}`}
            aria-pressed={filter === value}
            onClick={() => onFilter(value)}
          >
            {value === "open"
              ? `Open ${counts.open}`
              : value === "done"
                ? `Done ${counts.dismissed + counts.resolved}`
                : "All"}
          </button>
        ))}
        {present.length > 1 ? (
          <span className="lw-filters-rule" aria-hidden="true" />
        ) : null}
        {present.length > 1
          ? present.map((check) => {
              const on = checks.includes(check);
              return (
                <button
                  key={check}
                  type="button"
                  className={`lw-filter lw-filter-${check}${on ? " is-on" : ""}`}
                  aria-pressed={on}
                  onClick={() => {
                    const next = on
                      ? checks.filter((c) => c !== check)
                      : [...checks, check];
                    onChecks(next.length ? next : [...CHECKS]);
                  }}
                >
                  {CHECK_LABELS[check]}
                </button>
              );
            })
          : null}
      </div>
      {listed.length ? (
        <ul className="lw-issue-list" aria-label="Issues">
          {listed.map((issue) => (
            <IssueRow
              key={issue.id}
              issue={issue}
              placed={placed(issue)}
              active={issue.id === selected}
              onChoose={() => onChoose(issue)}
            />
          ))}
        </ul>
      ) : (
        <p className="lw-muted lw-small">
          {filter === "open" ? "Every issue is dealt with." : "Nothing here."}
        </p>
      )}
      <p className="lw-hint">
        <kbd>J</kbd> <kbd>K</kbd> move · <kbd>A</kbd> accept · <kbd>D</kbd> dismiss
      </p>
    </div>
  );
}
