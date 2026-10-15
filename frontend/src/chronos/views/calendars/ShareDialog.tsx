// Share a calendar with another writer. They see it in their own library,
// beside any calendar of theirs that happens to share its name.

import { useState } from "react";
import type { LibraryCalendar } from "../../api/types";
import { messageOf } from "../../api/errors";
import { useApi } from "../../deps";
import { useRefreshCalendars } from "../../hooks/mutations";
import { FormDialog } from "../../components/form/FormDialog";
import { SelectField, TextField } from "../../components/form/Fields";
import { useNotify } from "../../../components/ui/Toaster";

export const SHARE_ROLES = [
  { value: "reader", label: "Reader — may attach it to their books" },
  { value: "editor", label: "Editor — may also change it" },
];

export function ShareDialog({
  calendar,
  onClose,
}: {
  calendar: LibraryCalendar;
  onClose: () => void;
}) {
  const api = useApi();
  const refresh = useRefreshCalendars();
  const notify = useNotify();
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("reader");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const share = async () => {
    const who = username.trim();
    setBusy(true);
    setError(null);
    try {
      await api.shareCalendar(calendar.owner, calendar.id, who, role);
      await refresh();
      notify({ title: `Shared “${calendar.name}” with ${who}.` });
      onClose();
    } catch (e) {
      setError(messageOf(e, "Could not share this calendar."));
      setBusy(false);
    }
  };

  return (
    <FormDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Share “${calendar.name}”`}
      description="They will see it in their own library, beside any calendar of their own that happens to share its name."
      submitLabel="Share"
      busy={busy}
      error={error}
      canSubmit={Boolean(username.trim())}
      onSubmit={share}
    >
      <TextField
        label="Writer"
        value={username}
        placeholder="username"
        autoFocus
        onChange={setUsername}
      />
      <SelectField label="They may" value={role} options={SHARE_ROLES} onChange={setRole} />
    </FormDialog>
  );
}
