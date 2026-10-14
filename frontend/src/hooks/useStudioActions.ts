// Everything the studio changes, as mutations that refresh exactly what they
// touched. Components receive these as callbacks; none of them fetch.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../api/context";
import type { AskRequest, Job, Query, RefineRequest } from "../api/types";
import type { Composition } from "../logic/compose";
import { mergeJob } from "../logic/topics";
import { keys } from "./keys";
import { saveComposition } from "./saveComposition";

export function useStudioActions() {
  const api = useApi();
  const client = useQueryClient();
  const remember = (job: Job) =>
    client.setQueryData<Job[]>(keys.jobs, (list) => mergeJob(list ?? [], job));
  const refresh = (...queryKeys: (readonly unknown[])[]) =>
    Promise.all(queryKeys.map((queryKey) => client.invalidateQueries({ queryKey })));

  // Three ways to ask, each its own mutation so a failure shows only where it
  // happened: the ask box, "Dig deeper", or a failed topic's "Ask again".
  const asking = () => ({
    mutationFn: (request: AskRequest) => api.ask(request),
    onSuccess: remember,
  });
  const ask = useMutation(asking());
  const digDeeper = useMutation(asking());
  const retry = useMutation(asking());
  const approvePlan = useMutation({
    mutationFn: ({ id, queries }: { id: string; queries: Query[] }) =>
      api.approvePlan(id, queries),
    onSuccess: remember,
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancel(id),
    onSuccess: (job) => {
      remember(job);
      // A cancelled steer: the draft's own note that one is running is stale.
      if (job.refines) return refresh(keys.drafts);
    },
  });
  const refine = useMutation({
    mutationFn: ({ slug, request }: { slug: string; request: RefineRequest }) =>
      api.refine(slug, request),
    onSuccess: (job) => {
      remember(job);
      return refresh(keys.inbox, keys.drafts);
    },
  });
  const keep = useMutation({
    mutationFn: (slug: string) => api.acceptDraft(slug),
    onSuccess: () => refresh(keys.jobs, keys.inbox, keys.notes),
  });
  const close = useMutation({
    mutationFn: (slug: string) => api.closeDraft(slug),
    onSuccess: () => refresh(keys.jobs, keys.inbox),
  });
  const discard = useMutation({
    mutationFn: (slug: string) => api.discardDraft(slug),
    onSuccess: () => refresh(keys.jobs, keys.inbox),
  });
  const save = useMutation({
    mutationFn: ({
      comp,
      onImported,
    }: {
      comp: Composition;
      onImported: (media: ReadonlyMap<string, string>) => void;
    }) => saveComposition(api, comp, onImported),
    // Sources moved out of the inbox, so every open draft may have been relinked.
    onSuccess: () => refresh(keys.jobs, keys.inbox, keys.drafts, keys.notes),
  });

  return { ask, digDeeper, retry, approvePlan, cancel, refine, keep, close, discard, save };
}

export type StudioActions = ReturnType<typeof useStudioActions>;
