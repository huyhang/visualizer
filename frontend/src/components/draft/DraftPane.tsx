import { useState } from "react";
import type { ArticleRef, Draft, Job, Query, RefineRequest } from "../../api/types";
import { deepDiveQuestion } from "../../logic/deepDive";
import { slugOf } from "../../logic/format";
import type { TopicNode } from "../../logic/topics";
import { EmptyState } from "../ui/EmptyState";
import { Skeleton } from "../ui/Skeleton";
import type { DraftActions, ImageToAdd } from "./actions";
import { DigDeeperDialog } from "./DigDeeperDialog";
import { DraftView } from "./DraftView";
import { JobProgress } from "./JobProgress";
import { PlanCard } from "./PlanCard";
import { ClosedCard, FailedCard } from "./StatusCards";
import { SteerDialog } from "./SteerDialog";
import { TopicHeader } from "./TopicHeader";

/** What the draft pane can do to the world, each a promise the studio fulfils. */
export interface DraftHandlers {
  cancel(job: Job): Promise<unknown>;
  approve(job: Job, queries: Query[]): Promise<unknown>;
  retry(job: Job): Promise<unknown>;
  digDeeper(question: string, parent: Job): Promise<unknown>;
  steer(slug: string, request: RefineRequest): Promise<unknown>;
  keep(slug: string): Promise<unknown>;
  close(slug: string): Promise<unknown>;
  discard(slug: string): Promise<unknown>;
}

/** Each error a handler's last attempt left, shown where it was tried. */
export interface DraftErrors {
  retry: string | null;
  digDeeper: string | null;
  steer: string | null;
}

/** What the note pane offers the draft: adding material, and knowing what is in. */
export interface NoteBridge {
  addText(text: string, draft: string): void;
  hasText(text: string): boolean;
  addImage(image: ImageToAdd): void;
  hasImage(draft: string, index: number): boolean;
}

export interface DraftPaneProps {
  world: string;
  topic: TopicNode | null;
  path: TopicNode[];
  draft: Draft | undefined;
  draftError: string | null;
  handlers: DraftHandlers;
  pending: Record<keyof DraftHandlers, boolean>;
  errors: DraftErrors;
  /** A dialog closed: what its last attempt failed with no longer applies. */
  onDialogClosed: () => void;
  note: NoteBridge;
  previewUrl: (slug: string, index: number) => string;
  linkTo: DraftActions["linkTo"];
  articleUrl: (ref: ArticleRef) => string;
  onSelect: (id: string) => void;
}

type Dialog =
  { kind: "deeper"; passage: string } | { kind: "steer"; distrust: string[] } | null;

export function DraftPane(props: DraftPaneProps) {
  const { topic } = props;
  const [dialog, setDialog] = useState<Dialog>(null);

  if (!topic) {
    return (
      <section className="st-pane st-draft" aria-label="Draft">
        <EmptyState icon="book" title="Pick a topic, or ask a new question">
          The researcher searches the web, reads the pages, checks every quote against its
          source, and writes you a cited draft. Take what you like into a note.
        </EmptyState>
      </section>
    );
  }

  const { job } = topic;
  const actions: DraftActions = {
    ...props.note,
    digDeeper: (passage) => setDialog({ kind: "deeper", passage }),
    steer: (distrust = []) => setDialog({ kind: "steer", distrust }),
    linkTo: props.linkTo,
  };

  async function run(task: () => Promise<unknown>, after?: () => void) {
    try {
      await task();
      after?.();
    } catch {
      /* the mutation's error is shown where it happened */
    }
  }

  function closeDialog() {
    setDialog(null);
    props.onDialogClosed();
  }

  const slug = job.draft ? slugOf(job.draft) : "";
  const decide = {
    keep: () => props.handlers.keep(slug),
    done: () => props.handlers.close(slug),
    discard: () => props.handlers.discard(slug),
  };

  return (
    <section className="st-pane st-draft" aria-label="Draft">
      <div className="st-scroll st-draft-scroll" key={job.id}>
        <div className="st-draft-inner st-fade-in">
          {topic.status === "ready" ? (
            props.draft && props.draft.draft === job.draft ? (
              <DraftView
                topic={topic}
                path={props.path}
                draft={props.draft}
                actions={actions}
                previewUrl={(index) => props.previewUrl(slug, index)}
                decisions={{
                  pending: {
                    keep: props.pending.keep,
                    done: props.pending.close,
                    discard: props.pending.discard,
                  },
                  decide: (decision) => run(decide[decision]),
                }}
                steerPlan={{
                  approving: props.pending.approve,
                  cancelling: props.pending.cancel,
                  onApprove: (steer, queries) =>
                    run(() => props.handlers.approve(steer, queries)),
                  onCancel: (steer) => run(() => props.handlers.cancel(steer)),
                }}
                onSelect={props.onSelect}
              />
            ) : props.draftError ? (
              <p className="st-error-text" role="alert">
                {props.draftError}
              </p>
            ) : (
              <>
                <TopicHeader
                  topic={topic}
                  path={props.path}
                  title={topic.title}
                  onSelect={props.onSelect}
                />
                <Skeleton lines={8} />
              </>
            )
          ) : (
            <>
              <TopicHeader
                topic={topic}
                path={props.path}
                title={topic.title}
                onSelect={props.onSelect}
              />
              {topic.status === "researching" ? (
                <JobProgress
                  job={job}
                  cancelling={props.pending.cancel}
                  onCancel={() => run(() => props.handlers.cancel(job))}
                />
              ) : topic.status === "needs-approval" ? (
                <PlanCard
                  job={job}
                  approving={props.pending.approve}
                  cancelling={props.pending.cancel}
                  onApprove={(queries) => run(() => props.handlers.approve(job, queries))}
                  onCancel={() => run(() => props.handlers.cancel(job))}
                />
              ) : topic.status === "failed" ? (
                <FailedCard
                  job={job}
                  retrying={props.pending.retry}
                  retryError={props.errors.retry}
                  onRetry={() => run(() => props.handlers.retry(job))}
                />
              ) : (
                <ClosedCard job={job} world={props.world} articleUrl={props.articleUrl} />
              )}
            </>
          )}
        </div>
      </div>
      {dialog?.kind === "deeper" ? (
        <DigDeeperDialog
          initial={deepDiveQuestion(dialog.passage, job.question)}
          parentTitle={topic.title}
          busy={props.pending.digDeeper}
          error={props.errors.digDeeper}
          onClose={closeDialog}
          onSubmit={(question) =>
            run(() => props.handlers.digDeeper(question, job), closeDialog)
          }
        />
      ) : null}
      {dialog?.kind === "steer" && props.draft ? (
        <SteerDialog
          sources={props.draft.sources}
          distrusted={dialog.distrust}
          busy={props.pending.steer}
          error={props.errors.steer}
          onClose={closeDialog}
          onSubmit={(feedback, exclude) =>
            run(
              () => props.handlers.steer(slug, { feedback, exclude_sources: exclude }),
              closeDialog,
            )
          }
        />
      ) : null}
    </section>
  );
}
