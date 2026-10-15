// Writing a goal, from anywhere: the goals screen, the inspector's goal pane,
// the palette. The editor waits for the goal it is opened on (and for the
// book's goals, which its prerequisite picker offers) before it mounts, so
// the form starts from the record rather than filling in under the writer.

import { useMemo, useState } from "react";
import { useGoals } from "../../hooks/queries";
import { useOptionalBookScope } from "../../components/shell/BookScope";
import type { GoalEditOptions } from "../../components/shell/Actions";
import { EMPTY_SLOT, type EditorSlot } from "../slot";
import { GoalEditor } from "./GoalEditor";

type Editing =
  { mode: "new"; options: GoalEditOptions } | { mode: "edit"; id: string } | null;

function GoalEditorMount({
  book,
  calendar,
  editing,
  onClose,
}: {
  book: string;
  calendar: string | null;
  editing: Exclude<Editing, null>;
  onClose: () => void;
}) {
  const { data: goals } = useGoals(book, calendar);
  if (!goals) return null;
  const goal =
    editing.mode === "edit" ? (goals.find((g) => g.id === editing.id) ?? null) : null;
  if (editing.mode === "edit" && !goal) return null;
  return (
    <GoalEditor
      key={goal ? goal.id : "new"}
      book={book}
      goal={goal}
      goals={goals}
      open
      onOpenChange={(open) => !open && onClose()}
      onSaved={editing.mode === "new" ? editing.options.onSaved : undefined}
    />
  );
}

export function useGoalEditors(): EditorSlot {
  const scope = useOptionalBookScope();
  const [editing, setEditing] = useState<Editing>(null);
  const writable = scope !== null && scope.canWrite;
  const actions = useMemo(
    () =>
      writable
        ? {
            newGoal: (options: GoalEditOptions = {}) =>
              setEditing({ mode: "new", options }),
            editGoal: (id: string) => setEditing({ mode: "edit", id }),
          }
        : {},
    [writable],
  );
  if (!scope || !writable) return EMPTY_SLOT;
  return {
    actions,
    element: editing ? (
      <GoalEditorMount
        book={scope.id}
        calendar={scope.calendar}
        editing={editing}
        onClose={() => setEditing(null)}
      />
    ) : null,
  };
}
