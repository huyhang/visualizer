// What the studio reads, as cached queries. Reading the job list never asks the
// GPU box how a job is going -- only fetching that one job does -- so
// `useWatchedJobs` polls each unsettled job and folds the answer back into the
// list, refreshing the list and the inbox once one settles.

import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../api/context";
import type { Job } from "../api/types";
import { pollInterval } from "../logic/progress";
import { isActive, mergeJob } from "../logic/topics";
import { slugOf } from "../logic/format";
import { keys } from "./keys";
import { useVisible } from "./useVisible";

const AVAILABILITY_MS = 60_000;

export function useAvailability() {
  const api = useApi();
  return useQuery({
    queryKey: keys.availability,
    queryFn: () => api.availability(),
    refetchInterval: AVAILABILITY_MS,
  });
}

export function useJobs() {
  const api = useApi();
  return useQuery({ queryKey: keys.jobs, queryFn: () => api.listJobs() });
}

export function useInbox() {
  const api = useApi();
  return useQuery({ queryKey: keys.inbox, queryFn: () => api.inbox() });
}

export function useDraft(slug: string | null) {
  const api = useApi();
  return useQuery({
    queryKey: keys.draft(slug ?? ""),
    queryFn: () => api.draft(slug!),
    enabled: !!slug,
  });
}

export function useNotes() {
  const api = useApi();
  return useQuery({ queryKey: keys.notes, queryFn: () => api.listNotes() });
}

export function useWatchedJobs(jobs: Job[]) {
  const api = useApi();
  const client = useQueryClient();
  const visible = useVisible();
  const watched = jobs.filter((job) => pollInterval(job, visible) !== false);

  useQueries({
    queries: watched.map((job) => ({
      queryKey: keys.job(job.id),
      queryFn: async () => {
        const fresh = await api.getJob(job.id);
        client.setQueryData<Job[]>(keys.jobs, (list) => mergeJob(list ?? [], fresh));
        if (!isActive(fresh)) {
          // Settling can change other jobs too: a refinement that replaced
          // its draft marks the job it refined superseded.
          void client.invalidateQueries({ queryKey: keys.jobs });
          void client.invalidateQueries({ queryKey: keys.inbox });
          if (fresh.draft)
            void client.invalidateQueries({ queryKey: keys.draft(slugOf(fresh.draft)) });
          if (fresh.refines)
            void client.invalidateQueries({ queryKey: keys.draft(slugOf(fresh.refines)) });
        }
        return fresh;
      },
      refetchInterval: (query: { state: { data?: Job } }) =>
        pollInterval(query.state.data ?? job, visible),
    })),
  });
}
