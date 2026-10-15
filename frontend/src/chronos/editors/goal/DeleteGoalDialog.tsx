// Deleting a goal: the one thing on this screen that cannot be taken back.
//
// The server refuses while threads serve the goal or other goals rest on it,
// and names them. So the confirmation says what points at it before asking --
// from the goal as last read -- and if the page was stale and the server
// refuses anyway, its own answer replaces ours and the offer becomes "take it
// out of them first". Detaching leaves their scenes and prose untouched.

import { useState } from "react";
import type { Goal } from "../../api/types";
import { keys, useGoals } from "../../hooks/queries";
import { useForget, useRefreshBook } from "../../hooks/mutations";
import { useThreads } from "../../hooks/useThreads";
import { useApi } from "../../deps";
import { messageOf } from "../../api/errors";
import {
  blockersFromRefusal,
  blockersOf,
  noBlockers,
  type Blockers,
} from "../../logic/goals/draft";
import { ConfirmDialog } from "../../components/form/ConfirmDialog";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { useNotify } from "../../../components/ui/Toaster";

function BlockerList({ blockers }: { blockers: Blockers }) {
  return (
    <>
      <p>This goal is still pointed at:</p>
      <ul className="cw-goal-blockers">
        {blockers.threads.map((t) => (
          <li key={`t:${t.id}`}>
            <strong>{t.title}</strong> — a thread serving it
          </li>
        ))}
        {blockers.goals.map((g) => (
          <li key={`g:${g.id}`}>
            <strong>{g.title}</strong> — a goal resting on it
          </li>
        ))}
      </ul>
      <p className="cw-muted">
        Deleting takes it out of each of them. Their own scenes and prose are untouched.
      </p>
    </>
  );
}

export function DeleteGoalDialog({
  book,
  goal,
  open,
  onOpenChange,
  onDeleted,
}: {
  book: string;
  goal: Goal;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: () => void;
}) {
  const api = useApi();
  const refresh = useRefreshBook();
  const forget = useForget();
  const inspector = useInspector();
  const notify = useNotify();
  const { calendar } = useBookScope();
  const { get } = useThreads(book);
  const { data: goals } = useGoals(book, calendar);
  const [refusal, setRefusal] = useState<Blockers | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const blockers = refusal ?? blockersOf(goal);
  const detach = !noBlockers(blockers);

  const close = (next: boolean) => {
    if (!next) {
      setRefusal(null);
      setError(null);
    }
    onOpenChange(next);
  };

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.deleteGoal(book, goal.id, goal.rev, detach);
      inspector.forget({ kind: "goal", id: goal.id });
      forget([...keys.inBook(book), "goal", goal.id]);
      await refresh(book);
      notify({ title: `Deleted “${goal.title}”.` });
      close(false);
      onDeleted?.();
    } catch (e) {
      const named = blockersFromRefusal(
        e,
        (id) => get(id)?.title,
        (id) => goals?.find((g) => g.id === id)?.title,
      );
      if (named) setRefusal(named);
      else setError(messageOf(e, "Could not delete the goal."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={close}
      title={`Delete “${goal.title}”?`}
      confirmLabel={detach ? "Delete anyway" : "Delete"}
      onConfirm={remove}
      busy={busy}
      error={error}
    >
      {detach ? <BlockerList blockers={blockers} /> : <p>Nothing points at it.</p>}
    </ConfirmDialog>
  );
}
