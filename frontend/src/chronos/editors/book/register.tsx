// Starting a book and changing its settings. Any signed-in writer may create
// a book and owns what they create, so "New book" is always on offer; the
// settings only inside a book the writer may change.

import { useState } from "react";
import { useOptionalBookScope } from "../../components/shell/BookScope";
import type { EditorSlot } from "../slot";
import { BookEditor } from "./BookEditor";

export function useBookEditors(): EditorSlot {
  const scope = useOptionalBookScope();
  const [open, setOpen] = useState<"new" | "edit" | null>(null);
  const record = scope?.book ?? null;
  const canEdit = Boolean(scope?.canWrite && record);
  const close = () => setOpen(null);
  return {
    actions: {
      newBook: () => setOpen("new"),
      editBook: canEdit ? () => setOpen("edit") : undefined,
    },
    element:
      open === "new" ? (
        <BookEditor book={null} onClose={close} />
      ) : open === "edit" && record ? (
        <BookEditor book={record} onClose={close} key={record.id} />
      ) : null,
  };
}
