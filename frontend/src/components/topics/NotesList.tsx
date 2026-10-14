import { useState } from "react";
import type { NoteSummary } from "../../api/types";
import { timeAgo } from "../../logic/format";
import { Icon } from "../ui/Icon";

/** The world's research notes: open one to add material to it. */
export function NotesList({
  notes,
  activeSlug,
  onOpen,
}: {
  notes: NoteSummary[];
  activeSlug: string | null;
  onOpen: (slug: string) => void;
}) {
  const [filter, setFilter] = useState("");
  const shown = notes.filter((n) =>
    n.title.toLowerCase().includes(filter.trim().toLowerCase()),
  );
  if (!notes.length) {
    return (
      <p className="st-muted st-small st-pad">
        No research notes yet. Save one from a draft.
      </p>
    );
  }
  return (
    <div className="st-notes-list">
      {notes.length > 6 ? (
        <input
          className="st-input st-input-sm"
          type="search"
          placeholder="Filter notes…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="Filter notes"
        />
      ) : null}
      <ul>
        {shown.map((note) => (
          <li key={note.id}>
            <button
              type="button"
              className={`st-note-link${note.id === activeSlug ? " is-active" : ""}`}
              onClick={() => onOpen(note.id)}
            >
              <Icon name="note" size={14} />
              <span className="st-note-link-title">{note.title || note.id}</span>
              <span className="st-note-link-age">{timeAgo(note.updated)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
