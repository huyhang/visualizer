// The calendar a book is being read through, remembered per book.

import { useCallback, useState } from "react";
import type { CalendarAttachment } from "../api/types";
import { useDeps } from "../deps";
import { chooseCalendar, chosenCalendar } from "../logic/calendarView";

const NONE: CalendarAttachment[] = [];

export interface CalendarChoice {
  /** The chosen calendar's id, or null for the book's primary one. */
  calendar: string | null;
  calendars: CalendarAttachment[];
  choose: (id: string) => void;
}

export function useCalendarChoice(
  book: string | null,
  /** The book's calendars; undefined until the book has been read. */
  known: CalendarAttachment[] | undefined,
): CalendarChoice {
  const calendars = known ?? NONE;
  const { store } = useDeps();
  // Bumped on every choice: the store is the truth, this only asks React to read it again.
  const [, setVersion] = useState(0);
  const calendar = book ? chosenCalendar(store, book, known) : null;
  const choose = useCallback(
    (id: string) => {
      if (!book) return;
      chooseCalendar(store, book, id, calendars);
      setVersion((v) => v + 1);
    },
    [book, calendars, store],
  );
  return { calendar, calendars, choose };
}
