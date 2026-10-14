// The research studio: topics on the left, the draft being read in the middle,
// the note being written on the right. This component only wires: data comes
// from the hooks, changes go through `useStudioActions` and `useNoteComposer`,
// and the three panes receive what they show and what they may do as props.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useApi } from "../api/context";
import { messageOf } from "../api/errors";
import type { AskRequest, Job } from "../api/types";
import { askRequest, DEFAULT_OPTIONS } from "../logic/ask";
import { addedCount, type NewId } from "../logic/compose";
import { slugOf } from "../logic/format";
import { resolveTarget } from "../logic/refs";
import { buildTopicTree, findTopic, live, pathTo } from "../logic/topics";
import type { CompositionStore } from "../hooks/useComposition";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useNoteComposer } from "../hooks/useNoteComposer";
import { useSelection } from "../hooks/useSelection";
import { useStudioActions, type StudioActions } from "../hooks/useStudioActions";
import {
  useAvailability,
  useDraft,
  useInbox,
  useJobs,
  useNotes,
  useWatchedJobs,
} from "../hooks/useStudioData";
import type { DraftActions } from "./draft/actions";
import { DraftPane, type DraftHandlers } from "./draft/DraftPane";
import { NotePane } from "./note/NotePane";
import { StudioLayout, type PaneName } from "./StudioLayout";
import { blockedBy, StudioNotice } from "./StudioNotice";
import { TopicsPane } from "./topics/TopicsPane";
import { useNotify, type Notice } from "./ui/Toaster";

export function Studio({ store, newId }: { store: CompositionStore; newId: NewId }) {
  const api = useApi();
  const notify = useNotify();
  const narrow = useMediaQuery("(max-width: 1100px)");
  const [pane, setPane] = useState<PaneName>("topics");
  const [selected, select] = useSelection();

  const availability = useAvailability();
  const jobs = useJobs();
  const inbox = useInbox();
  const notes = useNotes();
  useWatchedJobs(jobs.data ?? []);
  const actions = useStudioActions();
  const composer = useNoteComposer({
    store,
    newId,
    save: actions.save,
    notify,
    onOpening: () => narrow && setPane("note"),
  });

  const topics = useMemo(
    () => (jobs.data ? buildTopicTree(jobs.data, inbox.data ?? []) : undefined),
    [jobs.data, inbox.data],
  );
  const topic = findTopic(topics ?? [], selected);
  const draft = useDraft(
    topic?.status === "ready" && topic.job.draft ? slugOf(topic.job.draft) : null,
  );
  useFollowRefinements(selected, jobs.data, select);

  const open = useCallback(
    (id: string) => {
      select(id);
      setPane("draft");
    },
    [select],
  );
  const linkTo = useCallback<DraftActions["linkTo"]>(
    (target) => {
      const ref = resolveTarget(target, api.world);
      return ref ? { ref, href: api.articleUrl(ref) } : null;
    },
    [api],
  );
  // Every way of asking opens the new topic once the box has it.
  const askWith =
    (mutation: StudioActions["ask"]) =>
    async (request: AskRequest): Promise<Job> => {
      const job = await mutation.mutateAsync(request);
      open(job.id);
      return job;
    };
  const handlers = draftHandlers(actions, askWith, notify, {
    deselect: () => select(null),
    noteUrl: (slug) => api.articleUrl({ db: api.world, col: "research", id: slug }),
  });

  const blocked = blockedBy(availability.data, jobs.error);
  if (blocked) return <StudioNotice blocked={blocked} />;

  return (
    <StudioLayout
      narrow={narrow}
      pane={pane}
      onPane={setPane}
      noteCount={addedCount(composer.comp)}
      draftLabel={topic ? topic.title : "Draft"}
      topics={
        <TopicsPane
          availability={availability.data}
          topics={topics}
          topicsError={errorOf(jobs)}
          notes={notes.data}
          selectedId={selected}
          activeNote={composer.activeNote}
          asking={actions.ask.isPending}
          askError={errorOf(actions.ask)}
          onAsk={askWith(actions.ask)}
          onSelect={open}
          onOpenNote={(slug) => void composer.openNote(slug)}
        />
      }
      draft={
        <DraftPane
          world={api.world}
          topic={topic}
          path={topic && topics ? pathTo(topics, topic.job.id) : []}
          draft={draft.data}
          draftError={errorOf(draft)}
          handlers={handlers}
          pending={{
            cancel: actions.cancel.isPending,
            approve: actions.approvePlan.isPending,
            retry: actions.retry.isPending,
            digDeeper: actions.digDeeper.isPending,
            steer: actions.refine.isPending,
            keep: actions.keep.isPending,
            close: actions.close.isPending,
            discard: actions.discard.isPending,
          }}
          errors={{
            retry: errorOf(actions.retry),
            digDeeper: errorOf(actions.digDeeper),
            steer: errorOf(actions.refine),
          }}
          onDialogClosed={() => {
            actions.digDeeper.reset();
            actions.refine.reset();
          }}
          note={composer.bridge}
          previewUrl={api.imagePreviewUrl}
          linkTo={linkTo}
          articleUrl={api.articleUrl}
          onSelect={open}
        />
      }
      note={<NotePane {...composer.paneProps} notes={notes.data ?? []} linkTo={linkTo} />}
    />
  );
}

/** A mutation's or query's last error, as a sentence for the writer. */
function errorOf(result: { error: unknown }): string | null {
  return result.error ? messageOf(result.error) : null;
}

/** What the draft pane's buttons do, in terms of the studio's mutations. */
function draftHandlers(
  actions: StudioActions,
  askWith: (mutation: StudioActions["ask"]) => (request: AskRequest) => Promise<Job>,
  notify: (notice: Notice) => void,
  { deselect, noteUrl }: { deselect: () => void; noteUrl: (slug: string) => string },
): DraftHandlers {
  return {
    cancel: (job) => actions.cancel.mutateAsync(job.id),
    approve: (job, queries) => actions.approvePlan.mutateAsync({ id: job.id, queries }),
    retry: (job) =>
      askWith(actions.retry)({
        ...askRequest(job.question, DEFAULT_OPTIONS),
        parent: job.parent,
      }),
    digDeeper: (question, parent) =>
      askWith(actions.digDeeper)(askRequest(question, DEFAULT_OPTIONS, parent.id)),
    keep: async (slug) => {
      const kept = await actions.keep.mutateAsync(slug);
      notify({
        title: "Kept as a research note",
        description: "The whole draft, with its sources, is now in your world.",
        action: { label: "Open", href: noteUrl(slugOf(kept.article)) },
      });
    },
    steer: async (slug, request) => {
      await actions.refine.mutateAsync({ slug, request });
      notify({
        title: "Researching again",
        description: "The new version will replace this draft.",
      });
    },
    close: async (slug) => {
      await actions.close.mutateAsync(slug);
      notify({
        title: "Draft closed",
        description: "Your notes keep what they took from it.",
      });
    },
    discard: async (slug) => {
      await actions.discard.mutateAsync(slug);
      deselect();
      notify({ title: "Draft discarded" });
    },
  };
}

/** A refinement that replaced the open draft carries the topic on: follow it. */
function useFollowRefinements(
  selected: string | null,
  jobs: Job[] | undefined,
  select: (id: string) => void,
) {
  useEffect(() => {
    if (!selected || !jobs) return;
    const current = live(selected, new Map(jobs.map((job) => [job.id, job])));
    if (current !== selected) select(current);
  }, [selected, jobs, select]);
}
