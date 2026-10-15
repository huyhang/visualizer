// What the workspace reads, as React Query hooks. One key per resource, so a
// write can say exactly what it made stale, and every screen reading the same
// thing shares one request and one answer.

import { useQuery } from "@tanstack/react-query";
import type { PageOptions } from "../api/ChronosApi";
import { useApi } from "../deps";

type Calendar = string | null;

/** Every key the workspace caches under, so invalidation never guesses. */
export const keys = {
  me: () => ["me"] as const,
  books: () => ["books"] as const,
  book: (book: string) => ["book", book] as const,
  /** Everything read inside one book: what a write to it can make stale. */
  inBook: (book: string) => ["in-book", book] as const,
  plotlines: (book: string, options: PageOptions) =>
    ["in-book", book, "plotlines", options] as const,
  plotline: (book: string, id: string, calendar: Calendar) =>
    ["in-book", book, "plotline", id, calendar] as const,
  report: (book: string, calendar: Calendar) =>
    ["in-book", book, "report", calendar] as const,
  goals: (book: string, calendar: Calendar) =>
    ["in-book", book, "goals", calendar] as const,
  goal: (book: string, id: string, calendar: Calendar) =>
    ["in-book", book, "goal", id, calendar] as const,
  graph: (book: string, calendar: Calendar) =>
    ["in-book", book, "graph", calendar] as const,
  timeline: (book: string, options: PageOptions) =>
    ["in-book", book, "timeline", options] as const,
  events: (book: string, options: PageOptions) =>
    ["in-book", book, "events", options] as const,
  event: (book: string, id: string, calendar: Calendar) =>
    ["in-book", book, "event", id, calendar] as const,
  entity: (book: string, database: string, collection: string, id: string) =>
    ["entity", book, database, collection, id] as const,
  calendars: () => ["calendars"] as const,
  worlds: () => ["worlds"] as const,
};

export function useMe() {
  const api = useApi();
  return useQuery({ queryKey: keys.me(), queryFn: () => api.me(), staleTime: Infinity });
}

export function useBooks() {
  const api = useApi();
  return useQuery({ queryKey: keys.books(), queryFn: () => api.listBooks() });
}

export function useBook(book: string | null) {
  const api = useApi();
  return useQuery({
    queryKey: keys.book(book ?? ""),
    queryFn: () => api.getBook(book ?? ""),
    enabled: book !== null,
  });
}

export function usePlotlines(book: string, options: PageOptions) {
  const api = useApi();
  return useQuery({
    queryKey: keys.plotlines(book, options),
    queryFn: () => api.listPlotlines(book, options),
    placeholderData: (previous) => previous,
  });
}

export function usePlotline(book: string, id: string | null, calendar: Calendar) {
  const api = useApi();
  return useQuery({
    queryKey: keys.plotline(book, id ?? "", calendar),
    queryFn: () => api.getPlotline(book, id ?? "", { calendar }),
    enabled: id !== null,
  });
}

export function useReport(book: string | null, calendar: Calendar) {
  const api = useApi();
  return useQuery({
    queryKey: keys.report(book ?? "", calendar),
    queryFn: () => api.bookIssues(book ?? "", { calendar }),
    enabled: book !== null,
  });
}

export function useGoals(book: string, calendar: Calendar) {
  const api = useApi();
  return useQuery({
    queryKey: keys.goals(book, calendar),
    queryFn: () => api.listGoals(book, { calendar }),
  });
}

export function useGoal(book: string, id: string | null, calendar: Calendar) {
  const api = useApi();
  return useQuery({
    queryKey: keys.goal(book, id ?? "", calendar),
    queryFn: () => api.getGoal(book, id ?? "", { calendar }),
    enabled: id !== null,
  });
}

export function useGraph(book: string | null, calendar: Calendar) {
  const api = useApi();
  return useQuery({
    queryKey: keys.graph(book ?? "", calendar),
    queryFn: () => api.getGraph(book ?? "", { calendar }),
    enabled: book !== null,
  });
}

export function useTimeline(book: string, options: PageOptions) {
  const api = useApi();
  return useQuery({
    queryKey: keys.timeline(book, options),
    queryFn: () => api.timelineEvents(book, options),
    placeholderData: (previous) => previous,
  });
}

export function useEvents(book: string, options: PageOptions) {
  const api = useApi();
  return useQuery({
    queryKey: keys.events(book, options),
    queryFn: () => api.listEvents(book, options),
    placeholderData: (previous) => previous,
  });
}

export function useEvent(book: string, id: string | null, calendar: Calendar) {
  const api = useApi();
  return useQuery({
    queryKey: keys.event(book, id ?? "", calendar),
    queryFn: () => api.getEvent(book, id ?? "", { calendar }),
    enabled: id !== null,
  });
}

/**
 * An Akasha article, read through the book that references it: the proxy
 * authorises against the book as well as the article, so the book is in the key.
 */
export function useEntity(
  book: string,
  ref: { database: string; collection: string; id: string } | null,
) {
  const api = useApi();
  return useQuery({
    queryKey: keys.entity(book, ref?.database ?? "", ref?.collection ?? "", ref?.id ?? ""),
    queryFn: () =>
      api.getEntity(book, ref?.database ?? "", ref?.collection ?? "", ref?.id ?? ""),
    enabled: ref !== null,
    staleTime: 5 * 60_000,
  });
}

export function useCalendars() {
  const api = useApi();
  return useQuery({ queryKey: keys.calendars(), queryFn: () => api.listCalendars() });
}

export function useWorlds() {
  const api = useApi();
  return useQuery({ queryKey: keys.worlds(), queryFn: () => api.listWorlds() });
}
