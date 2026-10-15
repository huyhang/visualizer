// The calendar library: named reckonings a writer keeps and attaches to books.
//
// A route rather than a dialog, and not book-scoped, because the point of a
// library is a calendar that outlives any one book -- and one the writer wants
// ready *before* creating the book that will use it. Attaching happens in the
// book form; this screen builds, shares and retires calendars.
//
// A calendar's identity is (owner, id): two writers will pick "imperial"
// independently, so a card names its owner whenever it is not you.

import { useState } from "react";
import type { LibraryCalendar } from "../../api/types";
import { messageOf } from "../../api/errors";
import { useApi, useDeps } from "../../deps";
import { useCalendars } from "../../hooks/queries";
import { useRefreshCalendars } from "../../hooks/mutations";
import { calendarHint } from "../../logic/calendars";
import { cycleSteps, libraryOrder, matchesCalendar } from "../../logic/books/calendarForm";
import { SearchField } from "../../components/common/Fields";
import { Page, PageHeader } from "../../components/common/Page";
import { QueryState } from "../../components/common/QueryState";
import { ConfirmDialog } from "../../components/form/ConfirmDialog";
import { CalendarEditor } from "./CalendarEditor";
import { ShareDialog } from "./ShareDialog";
import { Badge } from "../../../components/ui/Badge";
import { Button, IconButton } from "../../../components/ui/Button";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Icon } from "../../../components/ui/Icon";
import { useNotify } from "../../../components/ui/Toaster";

type Open =
  | { kind: "new" }
  | { kind: "edit"; calendar: LibraryCalendar }
  | { kind: "share"; calendar: LibraryCalendar }
  | { kind: "delete"; calendar: LibraryCalendar }
  | null;

/** The cycles as a chain of pills: hour → 24 → day → 30 → month. */
function CycleChain({ calendar }: { calendar: LibraryCalendar }) {
  const steps = cycleSteps(calendar.descriptor);
  if (calendar.descriptor.kind === "gregorian") {
    return (
      <div className="cw-cycle-chain">
        <span className="cw-cycle-pill is-earth">Earth</span>
        <span className="cw-cycle-pill">{calendar.descriptor.tick_unit ?? "day"}s</span>
      </div>
    );
  }
  if (!steps.length) return null;
  return (
    <div className="cw-cycle-chain" aria-hidden="true">
      {steps.map((step, n) =>
        step.kind === "unit" ? (
          <span key={n} className="cw-cycle-pill">
            {step.name}
          </span>
        ) : (
          <span key={n} className="cw-cycle-size">
            ×{step.size}
          </span>
        ),
      )}
      {calendar.descriptor.epoch_label ? (
        <span className="cw-cycle-epoch">{calendar.descriptor.epoch_label}</span>
      ) : null}
    </div>
  );
}

function CalendarCard({
  calendar,
  mine,
  onOpen,
}: {
  calendar: LibraryCalendar;
  mine: boolean;
  onOpen: (open: Open) => void;
}) {
  return (
    <article className="cw-calendar-card">
      <header className="cw-calendar-card-head">
        <span className="cw-calendar-card-mark" aria-hidden="true">
          <Icon name="calendar" size={16} />
        </span>
        <div className="cw-calendar-card-titles">
          <h2 className="cw-calendar-card-name">{calendar.name}</h2>
          <span className="cw-calendar-card-id">{calendar.qualified_id}</span>
        </div>
        {mine ? (
          <Badge tone="accent">Yours</Badge>
        ) : (
          <Badge>Shared by {calendar.owner}</Badge>
        )}
      </header>
      <CycleChain calendar={calendar} />
      <p className="cw-calendar-reading">{calendarHint(calendar.descriptor)}</p>
      {calendar.notes ? <p className="cw-calendar-card-notes">{calendar.notes}</p> : null}
      {mine ? (
        <footer className="cw-calendar-card-tools">
          <IconButton
            icon="edit"
            label="Edit this calendar"
            onClick={() => onOpen({ kind: "edit", calendar })}
          />
          <IconButton
            icon="user"
            label="Share this calendar"
            onClick={() => onOpen({ kind: "share", calendar })}
          />
          <IconButton
            icon="trash"
            label="Delete this calendar"
            onClick={() => onOpen({ kind: "delete", calendar })}
          />
        </footer>
      ) : null}
    </article>
  );
}

function DeleteCalendar({
  calendar,
  onClose,
}: {
  calendar: LibraryCalendar;
  onClose: () => void;
}) {
  const api = useApi();
  const refresh = useRefreshCalendars();
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const remove = async () => {
    setBusy(true);
    try {
      await api.deleteCalendar(calendar.owner, calendar.id, calendar.rev);
      await refresh();
      notify({ title: `Deleted “${calendar.name}”.` });
      onClose();
    } catch (e) {
      setError(messageOf(e, "Could not delete the calendar."));
      setBusy(false);
    }
  };
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Delete “${calendar.name}”?`}
      confirmLabel="Delete"
      busy={busy}
      error={error}
      onConfirm={remove}
    >
      <p>
        Books that already use it keep working — each one holds its own copy of the
        calendar, so nothing is re-dated. They simply stop being offered updates from this
        entry.
      </p>
    </ConfirmDialog>
  );
}

function Dialogs({ open, onClose }: { open: Open; onClose: () => void }) {
  if (!open) return null;
  switch (open.kind) {
    case "new":
      return <CalendarEditor calendar={null} onClose={onClose} />;
    case "edit":
      return <CalendarEditor calendar={open.calendar} onClose={onClose} />;
    case "share":
      return <ShareDialog calendar={open.calendar} onClose={onClose} />;
    case "delete":
      return <DeleteCalendar calendar={open.calendar} onClose={onClose} />;
  }
}

function Library({
  calendars,
  onOpen,
}: {
  calendars: LibraryCalendar[];
  onOpen: (open: Open) => void;
}) {
  const { user } = useDeps();
  const [query, setQuery] = useState("");
  if (!calendars.length) {
    return (
      <EmptyState
        icon="calendar"
        title="You have no saved calendars yet"
        action={
          <Button variant="primary" icon="plus" onClick={() => onOpen({ kind: "new" })}>
            New calendar
          </Button>
        }
      >
        Every book that counts time takes its calendar from here. A book with none simply
        shows plain ticks.
      </EmptyState>
    );
  }
  const shown = libraryOrder(calendars, user).filter((c) => matchesCalendar(c, query));
  return (
    <>
      <div className="cw-page-tools cw-calendar-tools">
        <SearchField
          value={query}
          onChange={setQuery}
          placeholder="Filter calendars…"
          label="Filter calendars"
        />
      </div>
      {shown.length ? (
        <div className="cw-calendar-grid">
          {shown.map((c) => (
            <CalendarCard
              key={c.qualified_id}
              calendar={c}
              mine={c.owner === user}
              onOpen={onOpen}
            />
          ))}
        </div>
      ) : (
        <EmptyState icon="search" title="No calendar matches">
          Nothing here contains every word of “{query}”.
        </EmptyState>
      )}
    </>
  );
}

export function CalendarsView() {
  const query = useCalendars();
  const [open, setOpen] = useState<Open>(null);
  return (
    <Page label="Calendars">
      <PageHeader
        eyebrow="Library"
        title="Your calendars"
        subtitle="Reckonings you can attach to any book. A book copies the calendar it attaches, so editing one here never re-dates a story you already wrote — the book offers you the update instead."
        actions={
          <Button variant="primary" icon="plus" onClick={() => setOpen({ kind: "new" })}>
            New calendar
          </Button>
        }
      />
      <QueryState query={query}>
        {(calendars) => <Library calendars={calendars} onOpen={setOpen} />}
      </QueryState>
      <Dialogs open={open} onClose={() => setOpen(null)} />
    </Page>
  );
}
