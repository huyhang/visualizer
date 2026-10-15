// The Writing Coach: Logos's local, rule-based reader. It runs when the page
// opens, when the dialect changes, and once typing pauses, and its findings are
// drawn in the prose beside the editor's. Ignoring a rule is remembered per
// account (shared with the series Review page); dismissing one finding lasts
// for this visit, as it always has.

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { messageOf } from "../api/errors";
import type { Dialect } from "../api/types";
import type { LogosDocument } from "../doc/types";
import { useDeps } from "../deps";

const PAUSE = 1800;

export function useCoach(book: string, read: () => LogosDocument) {
  const { api, preferences, timer } = useDeps();
  const [dialect, setDialectState] = useState<Dialect>(() => preferences.dialect());
  const [ignored, setIgnored] = useState(() => new Set(preferences.ignoredRules()));
  const [dismissed, setDismissed] = useState(() => new Set<string>());
  // Bumped when typing pauses: a new version is a new question for the Coach.
  const [version, setVersion] = useState(0);
  const handle = useRef<unknown>(null);

  const found = useQuery({
    queryKey: ["coach", book, dialect, version],
    queryFn: () => api.coach(book, read(), dialect),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  const schedule = useCallback(() => {
    timer.clear(handle.current);
    handle.current = timer.set(() => setVersion((n) => n + 1), PAUSE);
  }, [timer]);
  useEffect(() => () => timer.clear(handle.current), [timer]);

  const issues = useMemo(
    () =>
      (found.data?.issues ?? []).filter(
        (issue) => !ignored.has(issue.title) && !dismissed.has(issue.id),
      ),
    [found.data, ignored, dismissed],
  );

  return {
    issues,
    loading: found.isLoading,
    error: found.error
      ? messageOf(found.error, "The Coach could not read this draft.")
      : null,
    dialect,
    schedule,
    setDialect: (next: Dialect) => {
      preferences.setDialect(next);
      setDialectState(next);
    },
    dismiss: (id: string) => setDismissed((held) => new Set(held).add(id)),
    restore: (id: string) =>
      setDismissed((held) => {
        const next = new Set(held);
        next.delete(id);
        return next;
      }),
    ignoreRule: (title: string) => {
      preferences.ignoreRule(title);
      setIgnored((held) => new Set(held).add(title));
    },
  };
}

export type Coach = ReturnType<typeof useCoach>;
