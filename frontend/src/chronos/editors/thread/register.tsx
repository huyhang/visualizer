// Writing and arranging a thread: "New thread" and "Edit thread" from
// anywhere in a book, opening one editor over whatever is on screen.

import { useCallback, useMemo, useState } from "react";
import { useOptionalBookScope } from "../../components/shell/BookScope";
import { EMPTY_SLOT, type EditorSlot } from "../slot";
import { ThreadEditor } from "./ThreadEditor";

interface Open {
  id: string | null;
  /** A fresh editor each time it opens, so nothing carries over from the last one. */
  session: number;
}

export function useThreadEditors(): EditorSlot {
  const scope = useOptionalBookScope();
  const [open, setOpen] = useState<Open | null>(null);
  const start = useCallback(
    (id: string | null) => setOpen((was) => ({ id, session: (was?.session ?? 0) + 1 })),
    [],
  );
  const close = useCallback(() => setOpen(null), []);
  const writable = Boolean(scope?.canWrite);
  return useMemo(() => {
    if (!writable) return EMPTY_SLOT;
    return {
      actions: { newThread: () => start(null), editThread: (id: string) => start(id) },
      element: open ? (
        <ThreadEditor key={open.session} id={open.id} onClose={close} />
      ) : null,
    };
  }, [writable, open, start, close]);
}
