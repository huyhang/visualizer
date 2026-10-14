import { Popover } from "radix-ui";
import { useState } from "react";
import type { NoteSummary } from "../../api/types";
import type { Target } from "../../logic/compose";
import { Icon } from "../ui/Icon";

/** New note, or add to one of the world's notes -- a two-way switch. */
export function TargetPicker({
  target,
  targetTitle,
  notes,
  loading,
  onNew,
  onExisting,
}: {
  target: Target;
  targetTitle: string;
  notes: NoteSummary[];
  loading: boolean;
  onNew: () => void;
  onExisting: (slug: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const shown = notes.filter((n) =>
    (n.title || n.id).toLowerCase().includes(filter.trim().toLowerCase()),
  );

  return (
    <div className="st-segmented" role="radiogroup" aria-label="Where this goes">
      <button
        type="button"
        role="radio"
        aria-checked={target.kind === "new"}
        className={target.kind === "new" ? "is-on" : ""}
        onClick={onNew}
      >
        <Icon name="plus" size={14} /> New note
      </button>
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>
          <button
            type="button"
            role="radio"
            aria-checked={target.kind === "existing"}
            className={target.kind === "existing" ? "is-on" : ""}
            disabled={!notes.length || loading}
            title={notes.length ? undefined : "This world has no research notes yet"}
          >
            <Icon name="note" size={14} />
            <span className="st-ellipsis">
              {target.kind === "existing" ? targetTitle || target.slug : "Add to a note"}
            </span>
            <Icon name="chevronDown" size={12} />
          </button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content className="st-popover st-note-picker" sideOffset={6} align="end">
            <input
              className="st-input st-input-sm"
              type="search"
              placeholder="Find a note…"
              value={filter}
              autoFocus
              onChange={(e) => setFilter(e.target.value)}
              aria-label="Find a note"
            />
            <ul>
              {shown.map((note) => (
                <li key={note.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      onExisting(note.id);
                    }}
                  >
                    {note.title || note.id}
                  </button>
                </li>
              ))}
              {!shown.length ? (
                <li className="st-muted st-small">No note matches.</li>
              ) : null}
            </ul>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  );
}
