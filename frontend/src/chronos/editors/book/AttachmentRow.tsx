// One calendar a book keeps: which library calendar it names, what the
// switcher calls it, the span its culture kept it, and -- for Earth -- where
// this story's tick 0 falls. The common case is one row, and it should still
// feel like one field: the id and era boxes appear only once there is a
// second reckoning to tell apart.

import type { LibraryCalendar } from "../../api/types";
import { calendarHint, dateUnits } from "../../logic/calendars";
import {
  attachmentId,
  choose,
  libraryEntry,
  optionLabel,
  relabel,
  rowDescriptor,
  updateOffer,
  type AttachmentDraft,
} from "../../logic/books/attachments";
import { DateFields } from "../../components/form/DateFields";
import { Field, TextField } from "../../components/form/Fields";
import { Badge } from "../../../components/ui/Badge";
import { Button, IconButton } from "../../../components/ui/Button";

export interface RowControls {
  onChange: (next: AttachmentDraft) => void;
  onMove: (delta: number) => void;
  onPrimary: () => void;
  onRemove: () => void;
  onNewCalendar: () => void;
}

function LibraryChoice({
  row,
  library,
  onChange,
  onNewCalendar,
}: {
  row: AttachmentDraft;
  library: LibraryCalendar[];
  onChange: (next: AttachmentDraft) => void;
  onNewCalendar: () => void;
}) {
  const entry = libraryEntry(library, row.source);
  // A calendar deleted, or never shared with this reader, is still what the
  // book uses: it stays in the list, or the select would show something else.
  const lost = row.source && !entry ? `${row.source.owner}/${row.source.calendar}` : null;
  const value = row.source ? `${row.source.owner}/${row.source.calendar}` : "";
  return (
    <Field label="Calendar">
      <div className="cw-attach-choice">
        <select
          className="st-input"
          aria-label="Library calendar"
          value={value}
          onChange={(e) =>
            onChange(
              choose(row, library.find((c) => c.qualified_id === e.target.value) ?? null),
            )
          }
        >
          <option value="">— choose a calendar —</option>
          {lost ? <option value={lost}>{lost} (no longer in your library)</option> : null}
          {library.map((c) => (
            <option key={c.qualified_id} value={c.qualified_id}>
              {optionLabel(c, library)}
            </option>
          ))}
        </select>
        <Button size="sm" icon="plus" onClick={onNewCalendar}>
          New calendar
        </Button>
      </div>
    </Field>
  );
}

function UpdateOffer({
  row,
  library,
  onChange,
}: {
  row: AttachmentDraft;
  library: LibraryCalendar[];
  onChange: (next: AttachmentDraft) => void;
}) {
  const latest = updateOffer(row, library);
  if (!latest) return null;
  return (
    <div className="cw-update-offer" role="status">
      <p>
        <strong>{latest.qualified_id}</strong> has changed since this book copied it (your
        copy: revision {row.held?.rev}; the library: revision {latest.rev}). It now reads —{" "}
        {calendarHint(latest.descriptor)}
      </p>
      <Button size="sm" onClick={() => onChange({ ...row, tookUpdate: true })}>
        Use the newer version
      </Button>
    </div>
  );
}

function OriginField({
  row,
  library,
  onChange,
}: {
  row: AttachmentDraft;
  library: LibraryCalendar[];
  onChange: (next: AttachmentDraft) => void;
}) {
  const descriptor = rowDescriptor(row, library);
  if (descriptor?.kind !== "gregorian") return null;
  return (
    <Field
      label="This book's tick 0 fell on"
      hint="Where your story meets Earth's timeline. Asked here, because another book may use the same calendar centuries apart."
    >
      <div className="cw-attach-origin">
        <DateFields
          label="Tick 0"
          units={dateUnits(descriptor)}
          value={row.origin}
          onChange={(origin) => onChange({ ...row, origin })}
        />
        {descriptor.tick_unit !== "day" ? (
          <TextField
            label="UTC offset"
            value={row.offset}
            placeholder="Z"
            hint="Z, or a fixed offset like -08:00."
            onChange={(offset) => onChange({ ...row, offset })}
          />
        ) : null}
      </div>
    </Field>
  );
}

function EraFields({
  row,
  onChange,
}: {
  row: AttachmentDraft;
  onChange: (next: AttachmentDraft) => void;
}) {
  return (
    <div className="cw-form-row">
      <TextField
        label="Kept from tick"
        value={row.from}
        placeholder="start of the story"
        hint="Where this reckoning starts counting."
        onChange={(from) => onChange({ ...row, from })}
      />
      <TextField
        label="Until tick"
        value={row.until}
        placeholder="still kept"
        hint="When it stopped. Scenes outside read “before” or “after”."
        onChange={(until) => onChange({ ...row, until })}
      />
    </div>
  );
}

export function AttachmentRow({
  row,
  index,
  count,
  library,
  controls,
}: {
  row: AttachmentDraft;
  index: number;
  count: number;
  library: LibraryCalendar[];
  controls: RowControls;
}) {
  const many = count > 1;
  const { onChange } = controls;
  const descriptor = rowDescriptor(row, library);
  return (
    <li className="cw-attach-row">
      <div className="cw-attach-head">
        {index === 0 ? <Badge tone="accent">Primary</Badge> : <Badge>Also kept</Badge>}
        <span className="cw-attach-tools">
          {index > 0 ? (
            <Button size="sm" variant="ghost" onClick={controls.onPrimary}>
              Make primary
            </Button>
          ) : null}
          {many ? (
            <>
              <IconButton
                icon="arrowUp"
                label="Move up"
                disabled={index === 0}
                onClick={() => controls.onMove(-1)}
              />
              <IconButton
                icon="arrowDown"
                label="Move down"
                disabled={index === count - 1}
                onClick={() => controls.onMove(1)}
              />
            </>
          ) : null}
          <IconButton
            icon="x"
            label="Remove this calendar — no scene moves, only its labels go"
            onClick={controls.onRemove}
          />
        </span>
      </div>
      <LibraryChoice
        row={row}
        library={library}
        onChange={onChange}
        onNewCalendar={controls.onNewCalendar}
      />
      {descriptor ? (
        <p className="cw-calendar-reading">{calendarHint(descriptor)}</p>
      ) : null}
      <UpdateOffer row={row} library={library} onChange={onChange} />
      <div className="cw-form-row">
        <TextField
          label={many ? "Name" : "Name (optional)"}
          value={row.label}
          placeholder={index === 0 ? "Imperial Reckoning" : "Elvish Count"}
          hint={
            many
              ? "What the switcher calls this reckoning."
              : "Only shown once a book keeps more than one calendar."
          }
          onChange={(label) => onChange(relabel(row, label))}
        />
        {many ? (
          <TextField
            label="Id"
            value={attachmentId(row, index)}
            mono
            hint="Used in links; derived from the name until you change it."
            onChange={(id) => onChange({ ...row, id: id.trim(), idTouched: true })}
          />
        ) : null}
      </div>
      <OriginField row={row} library={library} onChange={onChange} />
      {many ? <EraFields row={row} onChange={onChange} /> : null}
    </li>
  );
}
