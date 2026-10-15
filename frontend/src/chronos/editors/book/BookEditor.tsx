// The book form: write a new book, or change an existing one's settings. One
// form for both, because they ask the same questions -- only the id
// (permanent) and the verb differ. A dialog, because it is a detour:
// cancelling leaves the page exactly as it was.
//
// The worlds and the calendar library are read before the form opens, so a
// chooser is never briefly empty and the only world is already chosen.

import { useState } from "react";
import type { Book, LibraryCalendar, World } from "../../api/types";
import { ChronosApiError, codeOf, messageOf } from "../../api/errors";
import { useApi } from "../../deps";
import { useCalendars, useWorlds } from "../../hooks/queries";
import { useRefreshBook } from "../../hooks/mutations";
import { useRoute } from "../../hooks/useRoute";
import { to } from "../../logic/route";
import {
  attachmentProblems,
  attachmentsBody,
  draftsFrom,
  type AttachmentDraft,
} from "../../logic/books/attachments";
import {
  bookBody,
  bookDraft,
  bookFailure,
  bookProblems,
  retitle,
  type BookDraft,
} from "../../logic/books/bookForm";
import { FormDialog } from "../../components/form/FormDialog";
import { Field, TextAreaField, TextField } from "../../components/form/Fields";
import { AttachmentList } from "./AttachmentList";
import { DeleteBook } from "./DeleteBook";
import { TerminusField } from "./TerminusField";
import { Button } from "../../../components/ui/Button";
import { Skeleton } from "../../../components/ui/Skeleton";
import { Modal } from "../../../components/ui/Modal";
import { useNotify } from "../../../components/ui/Toaster";

function WorldField({
  worlds,
  value,
  onChange,
}: {
  worlds: World[];
  value: string;
  onChange: (world: string) => void;
}) {
  if (!worlds.length) {
    return (
      <Field
        label="World"
        hint="Create one in Articles first — a book's characters and places are articles there."
      >
        <p className="cw-muted cw-small">You cannot read any worlds yet.</p>
      </Field>
    );
  }
  return (
    <Field
      label="World"
      hint="Where this book's characters, items and places live. Scenes can still reference another world; this is what the pickers search first."
    >
      <select
        className="st-input"
        aria-label="World"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— none yet —</option>
        {worlds.map((w) => (
          <option key={w.database} value={w.database}>
            {w.database}
          </option>
        ))}
      </select>
    </Field>
  );
}

function BookForm({
  book,
  worlds,
  library,
  onClose,
}: {
  book: Book | null;
  worlds: World[];
  library: LibraryCalendar[];
  onClose: () => void;
}) {
  const api = useApi();
  const refreshBook = useRefreshBook();
  const notify = useNotify();
  const { go } = useRoute();
  const editing = book !== null;
  const [draft, setDraft] = useState<BookDraft>(() => bookDraft(book, worlds));
  const [rows, setRows] = useState<AttachmentDraft[]>(() =>
    draftsFrom(book?.calendars ?? []),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const problems = [...bookProblems(draft), ...attachmentProblems(rows, library)];
  const started = editing || Boolean(draft.title.trim() || draft.id);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = bookBody(draft, attachmentsBody(rows, library), editing);
      const saved = book
        ? await api.updateBook(book.id, body, book.rev)
        : await api.createBook(draft.id, body);
      await refreshBook(saved.id);
      notify({
        title: editing ? "Book updated." : `Created “${saved.title || saved.id}”.`,
      });
      onClose();
      // Straight into a new book: its whole point is the thread about to be written.
      if (!editing) go(to.threads(saved.id));
    } catch (e) {
      const status = e instanceof ChronosApiError ? e.status : null;
      const fallback = messageOf(
        e,
        editing ? "Could not save the book." : "Could not create the book.",
      );
      setError(bookFailure(codeOf(e), status, draft.id, fallback));
      setBusy(false);
    }
  };

  const deleted = async () => {
    setDeleting(false);
    onClose();
    notify({ title: `Deleted “${draft.title.trim() || draft.id}”.` });
    // Away first: the screens about this book would otherwise re-read a book that is gone.
    go(to.books());
    await refreshBook(draft.id);
  };

  return (
    <>
      <FormDialog
        open
        onOpenChange={(open) => !open && onClose()}
        title={editing ? `Book settings · ${book.title || book.id}` : "New book"}
        description={
          editing
            ? "Saving replaces the book's details; its threads and scenes are untouched."
            : "Nothing is written until you create it."
        }
        submitLabel={editing ? "Save changes" : "Create book"}
        busy={busy}
        error={error ?? (started && problems.length ? problems.join(" ") : null)}
        canSubmit={problems.length === 0}
        onSubmit={save}
        wide
        extraActions={
          editing && book.permissions?.delete ? (
            <Button variant="danger" icon="trash" onClick={() => setDeleting(true)}>
              Delete book
            </Button>
          ) : undefined
        }
      >
        <div className="cw-form-row">
          <TextField
            label="Title"
            value={draft.title}
            placeholder="The Ember Pact"
            autoFocus
            hint="What you will call it. You can rename it later."
            onChange={(title) => setDraft(retitle(draft, title))}
          />
          <TextField
            label="Id"
            value={draft.id}
            placeholder="ember-pact"
            mono
            disabled={editing}
            hint={
              editing
                ? "A book's id is permanent — every link and grant points at it."
                : "Used in links and in the API. Derived from the title until you change it."
            }
            onChange={(id) => setDraft({ ...draft, id: id.trim(), idTouched: true })}
          />
        </div>
        <TextAreaField
          label="Overview"
          rows={3}
          value={draft.overview}
          placeholder="What this book is about (optional)"
          hint="No rule reads it; it is here so a shelf of books says more than a row of titles."
          onChange={(overview) => setDraft({ ...draft, overview })}
        />
        <WorldField
          worlds={worlds}
          value={draft.world}
          onChange={(world) => setDraft({ ...draft, world })}
        />
        <AttachmentList
          rows={rows}
          library={library}
          onChange={setRows}
          editing={editing}
        />
        {editing ? (
          <TerminusField
            book={book.id}
            value={draft.terminus}
            onChange={(terminus) => setDraft({ ...draft, terminus })}
          />
        ) : null}
      </FormDialog>
      {deleting && book ? (
        <DeleteBook book={book} onClose={() => setDeleting(false)} onDeleted={deleted} />
      ) : null}
    </>
  );
}

/** Waits for the worlds and the library; a list that could not be read offers none. */
export function BookEditor({ book, onClose }: { book: Book | null; onClose: () => void }) {
  const worlds = useWorlds();
  const calendars = useCalendars();
  const ready = (worlds.data || worlds.isError) && (calendars.data || calendars.isError);
  if (!ready) {
    return (
      <Modal
        open
        onOpenChange={(open) => !open && onClose()}
        title={book ? "Book settings" : "New book"}
      >
        <Skeleton lines={4} />
      </Modal>
    );
  }
  return (
    <BookForm
      book={book}
      worlds={worlds.data ?? []}
      library={calendars.data ?? []}
      onClose={onClose}
    />
  );
}
