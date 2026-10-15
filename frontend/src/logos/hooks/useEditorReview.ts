// The editor's review of this draft, through Logos's LLM-review routes:
//
//   availability  whether the GPU box can take a review now (asked every 30 s)
//   reviews       this section's kept reviews, newest first
//   review        the one being looked at -- the newest of this draft unless the
//                 writer chose another -- polled every few seconds while it runs
//   replies       issues the editor is replying to, asked after round by round
//                 until the reply lands, whether or not the last round got through
//
// Asking saves the draft first: the server reviews the draft it has, so words
// still on their way would be left out. Triage shows at once and is put back
// if the server refuses it.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { SectionAddress } from "../api/LogosApi";
import type { IssueStatus, Review, ReviewIssue, ReviewRequest } from "../api/types";
import { useDeps } from "../deps";
import { isActive, isReplying, latestReview, pollDelay } from "../logic/review";
import { useVisible } from "./useVisible";

export function reviewKeys(at: SectionAddress) {
  const base = ["llm-review", at.book, at.volume, at.section] as const;
  return {
    availability: ["llm-review", "availability"] as const,
    list: [...base, "list"] as const,
    review: (id: string | null) => [...base, "review", id] as const,
  };
}

export function useEditorReview(
  at: SectionAddress,
  draftId: string,
  settled: () => Promise<boolean>,
) {
  const { api, timer, visibility } = useDeps();
  const client = useQueryClient();
  const visible = useVisible(visibility);
  const keys = useMemo(() => reviewKeys(at), [at]);
  // A choice belongs to the draft it was made on; another draft opens on its own.
  const [chosen, setChosen] = useState<{ draft: string; id: string } | null>(null);
  const choose = useCallback(
    (id: string | null) => setChosen(id === null ? null : { draft: draftId, id }),
    [draftId],
  );

  const availability = useQuery({
    queryKey: keys.availability,
    queryFn: () => api.reviewAvailability(),
    refetchInterval: visible ? 30_000 : false,
    staleTime: 10_000,
  });

  const list = useQuery({ queryKey: keys.list, queryFn: () => api.reviews(at) });
  const viewing =
    (chosen?.draft === draftId ? chosen.id : null) ??
    latestReview(list.data ?? [], draftId)?.id ??
    null;

  const review = useQuery({
    queryKey: keys.review(viewing),
    queryFn: () => api.review(at, viewing as string),
    enabled: viewing !== null,
    refetchInterval: (query) => pollDelay(isActive(query.state.data?.state), visible),
  });

  // A finished review changes the list's counts; a new one heads it.
  const state = review.data?.state;
  useEffect(() => {
    if (state && !isActive(state)) void client.invalidateQueries({ queryKey: keys.list });
  }, [state, client, keys]);

  const patchIssue = useCallback(
    (reviewId: string, issue: ReviewIssue) =>
      client.setQueryData<Review>(keys.review(reviewId), (old) =>
        old?.issues
          ? { ...old, issues: old.issues.map((i) => (i.id === issue.id ? issue : i)) }
          : old,
      ),
    [client, keys],
  );

  // Replies are asked after one issue at a time, not with the review. Each
  // round ends by counting itself, which arms the next even when nothing came
  // back: a failed ask changes no issue, so nothing else would.
  const replying = (review.data?.issues ?? []).filter(isReplying);
  const replyingIds = replying.map((issue) => issue.id).join(",");
  const [rounds, setRounds] = useState(0);
  useEffect(() => {
    const reviewId = review.data?.id;
    const delay = pollDelay(replyingIds !== "", visible);
    if (!reviewId || delay === false) return;
    let live = true;
    const handle = timer.set(async () => {
      for (const id of replyingIds.split(",")) {
        try {
          patchIssue(reviewId, await api.issue(at, reviewId, id));
        } catch {
          // Nothing to show for this round; the next one asks again.
        }
      }
      if (live) setRounds((n) => n + 1);
    }, delay);
    return () => {
      live = false;
      timer.clear(handle);
    };
  }, [
    api,
    at,
    patchIssue,
    replyingIds,
    review.data?.id,
    review.dataUpdatedAt,
    rounds,
    timer,
    visible,
  ]);

  const ask = useMutation({
    mutationFn: async (request: Omit<ReviewRequest, "draft">) => {
      if (!(await settled()))
        throw new Error(
          "This draft has words that are not saved yet. Try again once it says Saved.",
        );
      return api.askForReview(at, { ...request, draft: draftId });
    },
    onSuccess: (started) => {
      client.setQueryData(keys.review(started.id), started);
      choose(started.id);
      // Ask straight away how it is going: a box with the model loaded is
      // already reading, and a fake one may be done.
      void client.invalidateQueries({ queryKey: keys.review(started.id) });
      void client.invalidateQueries({ queryKey: keys.list });
    },
  });

  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelReview(at, id),
    onSuccess: (cancelled) => client.setQueryData(keys.review(cancelled.id), cancelled),
  });

  const setStatus = useMutation({
    mutationFn: ({
      reviewId,
      issue,
      status,
    }: {
      reviewId: string;
      issue: ReviewIssue;
      status: IssueStatus;
    }) => api.setIssueStatus(at, reviewId, issue.id, status),
    onMutate: ({ reviewId, issue, status }) => {
      patchIssue(reviewId, { ...issue, status, dismissed_before: null });
      return { reviewId, issue };
    },
    onError: (_error, _vars, context) =>
      context && patchIssue(context.reviewId, context.issue),
    onSuccess: (issue, { reviewId }) => patchIssue(reviewId, issue),
  });

  const discuss = useMutation({
    mutationFn: ({
      reviewId,
      issue,
      text,
    }: {
      reviewId: string;
      issue: ReviewIssue;
      text: string;
    }) => api.discuss(at, reviewId, issue.id, text),
    onSuccess: (issue, { reviewId }) => patchIssue(reviewId, issue),
  });

  return {
    availability: availability.data,
    reviews: list.data ?? [],
    review: review.data ?? null,
    loading: list.isLoading || (viewing !== null && review.isLoading),
    error: review.error ?? list.error ?? null,
    viewing,
    choose,
    ask,
    cancel,
    setStatus,
    discuss,
  };
}

export type EditorReview = ReturnType<typeof useEditorReview>;
