// "Are you sure?", said with what is at stake. For the few things that cannot
// be taken back -- a deletion -- and for the server's refusals that offer a
// way through ("these threads use it; take it out of them first?").

import type { ReactNode } from "react";
import { Modal } from "../../../components/ui/Modal";
import { Button } from "../../../components/ui/Button";

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  children,
  confirmLabel,
  onConfirm,
  busy = false,
  danger = true,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  busy?: boolean;
  danger?: boolean;
  error?: string | null;
}) {
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant={danger ? "danger" : "primary"} busy={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="cw-confirm-body">{children}</div>
      {error ? (
        <p className="cw-form-error" role="alert">
          {error}
        </p>
      ) : null}
    </Modal>
  );
}
