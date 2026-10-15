// The book the workspace is inside, read once and shared: its record, the
// calendar it is being read through, and whether the reader may write to it.
// Every view inside a book takes these from here rather than asking again.

import { createContext, useContext, type ReactNode } from "react";
import type { Book } from "../../api/types";
import { useCalendarChoice, type CalendarChoice } from "../../hooks/useCalendarChoice";
import { useBook } from "../../hooks/queries";
import { isGone } from "../../api/errors";

export interface BookScopeValue extends CalendarChoice {
  /** The book's id: known from the address before the record arrives. */
  id: string;
  book: Book | undefined;
  canWrite: boolean;
}

const BookScopeContext = createContext<BookScopeValue | null>(null);

export function BookScope({ id, children }: { id: string; children: ReactNode }) {
  const { data, error } = useBook(id);
  // A book deleted, or no longer shared with this reader, offers nothing to write to.
  const book = isGone(error) ? undefined : data;
  const choice = useCalendarChoice(id, book?.calendars);
  const canWrite = book?.permissions?.write ?? false;
  return (
    <BookScopeContext.Provider value={{ id, book, canWrite, ...choice }}>
      {children}
    </BookScopeContext.Provider>
  );
}

export function useBookScope(): BookScopeValue {
  const scope = useContext(BookScopeContext);
  if (!scope) throw new Error("useBookScope() needs a <BookScope> above it.");
  return scope;
}

/** The scope when there is one -- the sidebar and palette work outside books too. */
export function useOptionalBookScope(): BookScopeValue | null {
  return useContext(BookScopeContext);
}
