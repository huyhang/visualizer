// A library calendar, new or edited. Created in the signed-in writer's own
// library -- the server refuses anyone else's. Saving hands the calendar back,
// so a caller that opened this to fill a gap (the book form's "New calendar")
// can choose it without reading the list again.

import { useState } from "react";
import type { LibraryCalendar } from "../../api/types";
import { ChronosApiError, codeOf, messageOf } from "../../api/errors";
import { useApi, useDeps } from "../../deps";
import { useRefreshCalendars } from "../../hooks/mutations";
import { draftFrom } from "../../logic/calendars";
import {
  calendarBody,
  calendarFailure,
  calendarFormProblems,
  type CalendarFormDraft,
} from "../../logic/books/calendarForm";
import { followTitle } from "../../logic/ids";
import { FormDialog } from "../../components/form/FormDialog";
import { TextAreaField, TextField } from "../../components/form/Fields";
import { CalendarDraftEditor } from "./CalendarDraftEditor";
import { useNotify } from "../../../components/ui/Toaster";

function initialDraft(calendar: LibraryCalendar | null): CalendarFormDraft {
  return {
    name: calendar?.name ?? "",
    id: calendar?.id ?? "",
    notes: calendar?.notes ?? "",
    calendar: draftFrom(calendar?.descriptor ?? null),
  };
}

export function CalendarEditor({
  calendar,
  onClose,
  onSaved,
}: {
  /** The calendar to edit, or null to write a new one. */
  calendar: LibraryCalendar | null;
  onClose: () => void;
  onSaved?: (saved: LibraryCalendar) => void;
}) {
  const api = useApi();
  const { user } = useDeps();
  const refresh = useRefreshCalendars();
  const notify = useNotify();
  const editing = calendar !== null;
  const [draft, setDraft] = useState(() => initialDraft(calendar));
  const [idTouched, setIdTouched] = useState(editing);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const problems = calendarFormProblems(draft);
  // Say what is missing only once the writer has started: an empty form scolding you is noise.
  const started = editing || Boolean(draft.name.trim() || draft.id);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = calendarBody(draft);
      const saved = calendar
        ? await api.updateCalendar(calendar.owner, calendar.id, body, calendar.rev)
        : await api.createCalendar(user, draft.id, body);
      await refresh();
      notify({ title: editing ? "Calendar updated." : `Created “${body.name}”.` });
      onSaved?.(saved);
      onClose();
    } catch (e) {
      const status = e instanceof ChronosApiError ? e.status : null;
      setError(
        calendarFailure(
          codeOf(e),
          status,
          draft.id,
          messageOf(e, "Could not save the calendar."),
        ),
      );
      setBusy(false);
    }
  };

  return (
    <FormDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={editing ? `Edit ${calendar.name}` : "New calendar"}
      description={
        editing
          ? "Books that already use this calendar keep the copy they took. They will be offered the change; none is re-dated behind your back."
          : "A reckoning you can attach to any book."
      }
      submitLabel={editing ? "Save changes" : "Create calendar"}
      busy={busy}
      error={error ?? (started && problems.length ? problems.join(" ") : null)}
      canSubmit={problems.length === 0}
      onSubmit={save}
      wide
    >
      <div className="cw-form-row">
        <TextField
          label="Name"
          value={draft.name}
          placeholder="Imperial Reckoning"
          autoFocus
          hint="What you will call it when attaching it to a book."
          onChange={(name) =>
            setDraft({ ...draft, name, id: followTitle(name, draft.id, idTouched) })
          }
        />
        <TextField
          label="Id"
          value={draft.id}
          placeholder="imperial"
          mono
          disabled={editing}
          hint={
            editing
              ? "A calendar's id is permanent."
              : "Used in links. Derived from the name until you change it."
          }
          onChange={(id) => {
            setIdTouched(true);
            setDraft({ ...draft, id: id.trim() });
          }}
        />
      </div>
      <TextAreaField
        label="Notes"
        rows={2}
        value={draft.notes}
        placeholder="What this calendar is for (optional)"
        onChange={(notes) => setDraft({ ...draft, notes })}
      />
      <CalendarDraftEditor
        draft={draft.calendar}
        onChange={(next) => setDraft({ ...draft, calendar: next })}
      />
    </FormDialog>
  );
}
