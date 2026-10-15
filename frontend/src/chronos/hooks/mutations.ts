// After a write: what to read again. A change to anything inside a book can
// change what the rules say about the rest of it -- a moved scene can clear a
// conflict three threads away -- so a write marks the whole book stale, and
// every screen showing part of it re-reads. That is what lets triage watch a
// fix land without being told.

import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { keys } from "./queries";

export function useRefreshBook() {
  const client = useQueryClient();
  return useCallback(
    (book: string) =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.inBook(book) }),
        client.invalidateQueries({ queryKey: keys.book(book) }),
        client.invalidateQueries({ queryKey: keys.books() }),
      ]),
    [client],
  );
}

/**
 * Forget what was read about records that have gone, so the refresh after a
 * delete does not ask for them again from a screen about to close.
 */
export function useForget() {
  const client = useQueryClient();
  return useCallback(
    (...prefixes: readonly unknown[][]) => {
      for (const queryKey of prefixes) client.removeQueries({ queryKey });
    },
    [client],
  );
}

export function useRefreshCalendars() {
  const client = useQueryClient();
  return useCallback(
    () => client.invalidateQueries({ queryKey: keys.calendars() }),
    [client],
  );
}
