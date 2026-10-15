import type { SaveState } from "../../logic/autosave";
import type { SaveStatus as Status } from "../../hooks/useDraftSession";

export const SAVE_LABELS: Record<SaveState, string> = {
  local: "Saved on this device",
  saving: "Saving…",
  saved: "Saved",
  offline: "Offline · saved on this device",
  conflict: "Conflict preserved",
  invalid: "Needs attention",
};

/** Where the words are: on this device, on their way, saved, or in trouble. */
export function SaveStatus({ status }: { status: Status }) {
  const label = SAVE_LABELS[status.state];
  return (
    <span
      className="lw-save"
      data-state={status.state}
      title={status.message ?? label}
      role="status"
      aria-live="polite"
    >
      <span className="lw-save-dot" aria-hidden="true" />
      <span className="lw-save-label">{label}</span>
    </span>
  );
}
