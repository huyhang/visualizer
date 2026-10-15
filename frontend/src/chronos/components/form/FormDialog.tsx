// A dialog that is a form: a title, the fields, and Save / Cancel. Submitting
// with Enter works; a refusal from the server shows above the buttons rather
// than in a toast, beside the fields it is about.

import type { FormEvent, ReactNode } from "react";
import { Modal } from "../../../components/ui/Modal";
import { Button } from "../../../components/ui/Button";

export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  submitLabel = "Save",
  busy = false,
  error,
  onSubmit,
  canSubmit = true,
  wide = false,
  extraActions,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  submitLabel?: string;
  busy?: boolean;
  /** What the server or the form said is wrong, if anything. */
  error?: string | null;
  onSubmit: () => void;
  canSubmit?: boolean;
  wide?: boolean;
  /** Left of Cancel: "Delete", say. */
  extraActions?: ReactNode;
}) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (canSubmit && !busy) onSubmit();
  };
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      wide={wide}
      className="cw-form-dialog"
    >
      <form className="cw-form" onSubmit={submit} noValidate>
        <div className="cw-form-fields">{children}</div>
        {error ? (
          <p className="cw-form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="cw-form-foot">
          {extraActions ? <div className="cw-form-extra">{extraActions}</div> : null}
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" busy={busy} disabled={!canSubmit}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
