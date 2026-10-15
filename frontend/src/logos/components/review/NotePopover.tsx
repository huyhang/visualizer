// The note behind an underline, beside the words it is about. Anchored to the
// underline itself -- looked up afresh whenever it is measured, because the
// editor redraws its decorations as the writer types -- and closed when the
// words are gone. Focus stays in the prose: clicking a note to read it should
// not take the caret away. On a phone it rises as a sheet from the bottom.

import { Dialog, Popover } from "radix-ui";
import { useMemo } from "react";
import type { ReviewReference } from "../../api/types";
import { useMediaQuery } from "../../../hooks/useMediaQuery";
import type { Note, NoteActions } from "../../logic/notes";
import { NoteCard } from "./NoteCard";

const underline = (id: string) =>
  document.querySelector<HTMLElement>(`[data-annotation="${CSS.escape(id)}"]`);

export function NotePopover({
  note,
  references,
  actions,
  onClose,
}: {
  note: Note | null;
  references?: ReviewReference[];
  actions: NoteActions;
  onClose: () => void;
}) {
  const phone = useMediaQuery("(max-width: 820px)");
  const anchor = useMemo(
    () => ({
      current: {
        getBoundingClientRect: () =>
          (note && underline(note.id)?.getBoundingClientRect()) ??
          new DOMRect(-1000, -1000, 0, 0),
      },
    }),
    [note],
  );
  if (!note) return null;
  const card = (
    <NoteCard
      note={note}
      actions={actions}
      placed
      references={references}
      variant="popover"
    />
  );

  if (phone) {
    return (
      <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
        <Dialog.Portal>
          <Dialog.Overlay className="lw-sheet-overlay" />
          <Dialog.Content
            className="lw-sheet"
            aria-describedby={undefined}
            onOpenAutoFocus={(event) => event.preventDefault()}
          >
            <span className="lw-sheet-grip" aria-hidden="true" />
            <Dialog.Title className="st-sr-only">
              Note on “{note.source === "coach" ? note.issue.excerpt : note.issue.quote}”
            </Dialog.Title>
            {card}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    );
  }
  return (
    <Popover.Root open onOpenChange={(open) => !open && onClose()}>
      <Popover.Anchor virtualRef={anchor} />
      <Popover.Portal>
        <Popover.Content
          className="st-popover lw-note-bubble"
          side="bottom"
          align="start"
          sideOffset={8}
          collisionPadding={16}
          onOpenAutoFocus={(event) => event.preventDefault()}
          onCloseAutoFocus={(event) => event.preventDefault()}
        >
          {card}
          <Popover.Arrow className="st-popover-arrow" width={14} height={7} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
