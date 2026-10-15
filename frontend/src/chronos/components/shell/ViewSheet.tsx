// On a phone, what the sidebar keeps beside the screens -- the calendar the
// book is read in, who is followed, the library, the way back to the classic
// page -- lives in a sheet that rises from the bottom, so the strip above the
// screen holds only where to go. Over the shared nav, not under it.

import { Dialog } from "radix-ui";
import type { ReactNode } from "react";
import { Icon } from "../../../components/ui/Icon";

export function ViewSheet({
  open,
  onOpenChange,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="st-overlay cw-sheet-overlay" />
        <Dialog.Content className="cw-sheet" aria-describedby={undefined}>
          <div className="cw-sheet-grip" aria-hidden="true" />
          <header className="cw-sheet-head">
            <Dialog.Title className="cw-sheet-title">View</Dialog.Title>
            <Dialog.Close className="st-icon-btn" aria-label="Close">
              <Icon name="x" />
            </Dialog.Close>
          </header>
          <div className="cw-sheet-body">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
