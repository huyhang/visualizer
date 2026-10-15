// The book's threads, named and painted, from the story graph: one request
// that every screen shares, so a thread has one name and one colour throughout.

import { useMemo } from "react";
import type { Graph } from "../api/types";
import { threadPaints, type ThreadPaint } from "../logic/threadColors";
import { useGraph } from "./queries";

export interface ThreadInfo extends ThreadPaint {
  id: string;
  title: string;
}

export interface Threads {
  list: ThreadInfo[];
  get: (id: string) => ThreadInfo | undefined;
  graph: Graph | undefined;
}

export function threadsOf(graph: Graph | undefined): ThreadInfo[] {
  const plotlines = graph?.plotlines ?? [];
  const paints = threadPaints(plotlines.map((p) => p.id));
  return plotlines.map((p) => ({
    id: p.id,
    title: p.title || p.id,
    ...(paints.get(p.id) as ThreadPaint),
  }));
}

export function useThreads(book: string | null, calendar: string | null = null): Threads {
  const { data: graph } = useGraph(book, calendar);
  return useMemo(() => {
    const list = threadsOf(graph);
    const byId = new Map(list.map((t) => [t.id, t]));
    return { list, get: (id: string) => byId.get(id), graph };
  }, [graph]);
}
