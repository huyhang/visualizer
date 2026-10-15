// Deleting a book takes its plotlines and scenes with it, hard, with no
// history to restore from. So the confirmation is built from what is actually
// in there: a writer about to lose seventeen scenes is told the number
// seventeen, and types the book's id before it goes.

import { useState } from "react";
import type { Book } from "../../api/types";
import { messageOf } from "../../api/errors";
import { useApi } from "../../deps";
import { useEvents } from "../../hooks/queries";
import { countPhrase, needsTypedConfirmation } from "../../logic/books/bookForm";
import { ConfirmDialog } from "../../components/form/ConfirmDialog";

export function DeleteBook({
  book,
  onClose,
  onDeleted,
}: {
  book: Book;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const api = useApi();
  // One cheap page of one: the total is all this needs.
  const { data, isError, isPending } = useEvents(book.id, { perPage: 1 });
  const scenes = isError ? null : (data?.total ?? null);
  const plotlines = book.plotlines.length;
  const gated = needsTypedConfirmation(plotlines, scenes);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const label = book.title || book.id;

  const remove = async () => {
    // ConfirmDialog has no disabled state, so a mismatch is said rather than ignored.
    if (gated && typed.trim() !== book.id) {
      setError(`Type ${book.id} to confirm.`);
      return;
    }
    setBusy(true);
    try {
      await api.deleteBook(book.id, book.rev);
      onDeleted();
    } catch (e) {
      setError(messageOf(e, "Could not delete the book."));
      setBusy(false);
    }
  };

  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Delete “${label}”?`}
      confirmLabel="Delete this book"
      busy={busy || isPending}
      error={error}
      onConfirm={remove}
    >
      {gated ? (
        <>
          <p>
            This deletes {countPhrase(plotlines, scenes)} along with the book. It cannot be
            undone.
          </p>
          <p className="cw-muted">
            The characters, items and places its scenes reference are articles, and are not
            touched.
          </p>
          <label className="cw-field">
            <span className="cw-field-label">Type {book.id} to confirm</span>
            <input
              className="st-input cw-mono"
              aria-label="Book id"
              placeholder={book.id}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
            />
          </label>
        </>
      ) : (
        <p>It has no plotlines or scenes yet.</p>
      )}
    </ConfirmDialog>
  );
}
