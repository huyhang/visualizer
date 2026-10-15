// The calendars a book keeps. A world may count time more than one way -- the
// Imperial calendar runs the length of the story, the Elvish one stops when
// the elves do -- and both date the same scenes. None at all is how a book
// says "plain numbers". The rows are the form's; this only arranges them.

import { useState } from "react";
import type { LibraryCalendar } from "../../api/types";
import {
  MAX_CALENDARS,
  blankAttachment,
  choose,
  makePrimary,
  moveRow,
  type AttachmentDraft,
} from "../../logic/books/attachments";
import { Field } from "../../components/form/Fields";
import { CalendarEditor } from "../../views/calendars/CalendarEditor";
import { AttachmentRow } from "./AttachmentRow";
import { Button } from "../../../components/ui/Button";

export function AttachmentList({
  rows,
  library,
  onChange,
  editing,
}: {
  rows: AttachmentDraft[];
  library: LibraryCalendar[];
  onChange: (rows: AttachmentDraft[]) => void;
  editing: boolean;
}) {
  // Which row asked for a new calendar, so the one it makes is chosen for it.
  const [creatingFor, setCreatingFor] = useState<string | null>(null);
  const replace = (key: string, next: AttachmentDraft) =>
    onChange(rows.map((r) => (r.key === key ? next : r)));

  return (
    <Field
      label="Time"
      hint={
        editing
          ? "Changing this re-labels the book — every scene keeps its tick, so no timing moves and no finding changes."
          : "How this book counts time. Scenes sit at whole-number ticks; a calendar only decides how they read."
      }
    >
      {rows.length ? (
        <ol className="cw-attach-list">
          {rows.map((row, n) => (
            <AttachmentRow
              key={row.key}
              row={row}
              index={n}
              count={rows.length}
              library={library}
              controls={{
                onChange: (next) => replace(row.key, next),
                onMove: (delta) => onChange(moveRow(rows, n, delta)),
                onPrimary: () => onChange(makePrimary(rows, n)),
                onRemove: () => onChange(rows.filter((r) => r.key !== row.key)),
                onNewCalendar: () => setCreatingFor(row.key),
              }}
            />
          ))}
        </ol>
      ) : (
        <p className="cw-attach-none">
          No calendar: scenes are placed at whole-number ticks and read back as those
          numbers.
        </p>
      )}
      {rows.length < MAX_CALENDARS ? (
        <div className="cw-chip-row">
          <Button
            size="sm"
            icon="plus"
            onClick={() => onChange([...rows, blankAttachment()])}
          >
            {rows.length ? "Add another calendar" : "Add a calendar"}
          </Button>
        </div>
      ) : null}
      {creatingFor ? (
        <CalendarEditor
          calendar={null}
          onClose={() => setCreatingFor(null)}
          onSaved={(made) => {
            const row = rows.find((r) => r.key === creatingFor);
            if (row) replace(row.key, choose(row, made));
          }}
        />
      ) : null}
    </Field>
  );
}
