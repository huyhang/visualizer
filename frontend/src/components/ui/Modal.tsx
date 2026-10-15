import { Dialog } from "radix-ui";
import type { ReactNode } from "react";
import { Icon } from "./Icon";

/**
 * A field showing its own list -- a type-ahead's options -- takes Escape to
 * close that list. The dialog hears Escape first, so it has to leave it.
 */
function keepEscapeForOpenList(e: KeyboardEvent) {
  const target = e.target instanceof Element ? e.target : null;
  if (target?.closest('[role="combobox"][aria-expanded="true"]')) e.preventDefault();
}

/** A centred dialog: a title, an optional line under it, a body and a footer. */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  wide = false,
  className = "",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  /** Extra classes on the dialog, for a surface that shapes it differently. */
  className?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="st-overlay" />
        <Dialog.Content
          className={`st-modal${wide ? " is-wide" : ""} ${className}`.trim()}
          onEscapeKeyDown={keepEscapeForOpenList}
        >
          <header className="st-modal-head">
            <Dialog.Title className="st-modal-title">{title}</Dialog.Title>
            <Dialog.Close className="st-icon-btn" aria-label="Close">
              <Icon name="x" />
            </Dialog.Close>
          </header>
          {description ? (
            <Dialog.Description className="st-modal-desc">{description}</Dialog.Description>
          ) : (
            <Dialog.Description className="st-sr-only">{title}</Dialog.Description>
          )}
          <div className="st-modal-body">{children}</div>
          {footer ? <footer className="st-modal-foot">{footer}</footer> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
