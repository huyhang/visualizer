import { Dialog } from "radix-ui";
import type { ReactNode } from "react";
import { Icon } from "./Icon";

/** A centred dialog: a title, an optional line under it, a body and a footer. */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  wide = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="st-overlay" />
        <Dialog.Content className={`st-modal${wide ? " is-wide" : ""}`}>
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
