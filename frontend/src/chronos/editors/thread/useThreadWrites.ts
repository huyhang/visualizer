// The editor's writes: save, delete, and naming the book's ending. Each says
// what the server refused in the writer's words, and leaves the dialog open
// when there is something to decide -- someone else's newer copy, or threads
// that would lose their story if this one went.

import { useState } from "react";
import { codeOf, evidenceIds, messageOf } from "../../api/errors";
import { useApi } from "../../deps";
import { useRefreshBook } from "../../hooks/mutations";
import { bodyOf, type ThreadDraft } from "../../logic/plotline/draft";
import { useNotify } from "../../../components/ui/Toaster";

export type Refusal =
  | { kind: "message"; text: string }
  /** Someone saved this thread since it was opened. */
  | { kind: "stale" }
  /** Other threads continue into this one; deleting it would orphan them. */
  | { kind: "in-use"; dependents: string[] };

export function refusalOf(error: unknown, fallback: string): Refusal {
  if (codeOf(error) === "REVISION_CONFLICT") return { kind: "stale" };
  if (codeOf(error) === "PLOTLINE_IN_USE")
    return { kind: "in-use", dependents: evidenceIds(error, "plotlines") };
  return { kind: "message", text: messageOf(error, fallback) };
}

export function useThreadWrites(book: string, creating: boolean, rev: number | null) {
  const api = useApi();
  const refresh = useRefreshBook();
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<Refusal | null>(null);

  async function attempt<T>(work: () => Promise<T>, fallback: string): Promise<T | null> {
    setBusy(true);
    setRefusal(null);
    try {
      const result = await work();
      await refresh(book);
      return result;
    } catch (e) {
      setRefusal(refusalOf(e, fallback));
      return null;
    } finally {
      setBusy(false);
    }
  }

  const save = async (draft: ThreadDraft) => {
    const saved = await attempt(
      () =>
        creating
          ? api.createPlotline(book, draft.id, bodyOf(draft))
          : api.updatePlotline(book, draft.id, bodyOf(draft), rev ?? 0),
      "Could not save the thread.",
    );
    if (saved) notify({ title: creating ? "Thread created" : "Changes saved" });
    return saved;
  };

  const remove = async (id: string, inline = false) => {
    const done = await attempt(async () => {
      await api.deletePlotline(book, id, rev ?? 0, inline);
      return true;
    }, "Could not delete the thread.");
    if (done) notify({ title: inline ? "Thread absorbed and deleted" : "Thread deleted" });
    return Boolean(done);
  };

  const makeEnding = async (scene: string, title: string) => {
    const done = await attempt(async () => {
      await api.setTerminus(book, scene);
      return true;
    }, "Could not set the book's ending.");
    if (done) notify({ title: `“${title}” is now the book's ending` });
    return Boolean(done);
  };

  return { save, remove, makeEnding, busy, refusal, clearRefusal: () => setRefusal(null) };
}
