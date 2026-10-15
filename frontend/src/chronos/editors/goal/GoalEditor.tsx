// The goal form: write a new goal or change one. One form for both, because
// they ask the same questions -- only the id (permanent) and the verb differ.
// A dialog, so cancelling leaves the diagram exactly as it was.
//
// Both references are pickers over what the book already has, because the
// server refuses either if it names nothing.

import { useCallback, useState } from "react";
import type { Goal, GoalWrite } from "../../api/types";
import { useApi } from "../../deps";
import { useRefreshBook } from "../../hooks/mutations";
import {
  draftFor,
  goalBody,
  offerable,
  saveFailure,
  withId,
  withTitle,
  type GoalDraft,
} from "../../logic/goals/draft";
import { idProblem } from "../../logic/ids";
import { Chip } from "../../components/common/Chips";
import { Field, TextAreaField, TextField } from "../../components/form/Fields";
import { FormDialog } from "../../components/form/FormDialog";
import { TypeAhead, type Option } from "../../components/form/TypeAhead";
import { Button } from "../../../components/ui/Button";
import { useNotify } from "../../../components/ui/Toaster";
import { DeleteGoalDialog } from "./DeleteGoalDialog";

function Prerequisites({
  draft,
  goals,
  onChange,
}: {
  draft: GoalDraft;
  goals: Goal[];
  onChange: (dependsOn: string[]) => void;
}) {
  const titleOf = (id: string) => goals.find((g) => g.id === id)?.title ?? id;
  // Filtered in the browser: the book's goals are already in hand for the diagram.
  const search = useCallback(
    (query: string): Option<string>[] =>
      offerable(goals, draft, query).map((g) => ({
        key: g.id,
        value: g.id,
        label: g.title,
        hint: g.id,
      })),
    [goals, draft],
  );
  return (
    <Field label="Rests on" hint="Goals that must be met before this one.">
      <div className="cw-chip-row cw-goal-picked">
        {draft.dependsOn.length ? (
          draft.dependsOn.map((id) => (
            <Chip
              key={id}
              icon="x"
              tone="accent"
              title="Remove this prerequisite"
              onClick={() => onChange(draft.dependsOn.filter((d) => d !== id))}
            >
              {titleOf(id)}
            </Chip>
          ))
        ) : (
          <span className="cw-muted cw-small">Rests on nothing.</span>
        )}
      </div>
      <TypeAhead
        label="Add a prerequisite"
        placeholder="Add a prerequisite…"
        search={search}
        onPick={(id) => onChange([...draft.dependsOn, id])}
      />
    </Field>
  );
}

function DeliveringScene({
  book,
  draft,
  onChange,
}: {
  book: string;
  draft: GoalDraft;
  onChange: (scene: { id: string; title: string } | null) => void;
}) {
  const api = useApi();
  const search = useCallback(
    async (query: string): Promise<Option<{ id: string; title: string }>[]> =>
      (await api.listEvents(book, { filter: query, perPage: 8 })).events.map((e) => ({
        key: e.id,
        value: { id: e.id, title: e.title },
        label: e.title,
        hint: e.when,
      })),
    [api, book],
  );
  return (
    <Field
      label="Achieved at"
      hint="The scene that delivers it. Leave it empty until you have written one."
    >
      <div className="cw-chip-row cw-goal-picked">
        {draft.achievedAt ? (
          <Chip icon="x" tone="ok" title="Clear the scene" onClick={() => onChange(null)}>
            {draft.achievedTitle ?? draft.achievedAt}
          </Chip>
        ) : (
          <span className="cw-muted cw-small">No scene yet.</span>
        )}
      </div>
      <TypeAhead
        label="Choose the scene"
        placeholder="Search this book's scenes…"
        search={search}
        onPick={onChange}
      />
    </Field>
  );
}

export function GoalEditor({
  book,
  goal: current,
  goals,
  open,
  onOpenChange,
  onSaved,
}: {
  book: string;
  /** The goal to change, or null to write a new one. */
  goal: Goal | null;
  /** Every goal in the book, for the prerequisite picker and the id check. */
  goals: Goal[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: (saved: Goal) => void;
}) {
  const api = useApi();
  const refresh = useRefreshBook();
  const notify = useNotify();
  // The goal as the draft was made from it, kept while the form is open: Save
  // and Delete send its revision, so a list refetched meanwhile cannot let a
  // stale draft overwrite someone else's newer save.
  const [goal] = useState(current);
  const editing = goal !== null;
  const [draft, setDraft] = useState(() => draftFor(goal));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const idError = editing
    ? null
    : idProblem(
        draft.id,
        goals.map((g) => g.id),
      );

  const save = async () => {
    setBusy(true);
    setError(null);
    // A full replace; nulls are how a blank title and an unset scene are cleared.
    const body: GoalWrite = goalBody(draft);
    try {
      const saved = goal
        ? await api.updateGoal(book, goal.id, body, goal.rev)
        : await api.createGoal(book, draft.id, body);
      await refresh(book);
      notify({ title: editing ? "Goal updated." : `Created “${saved.title}”.` });
      onOpenChange(false);
      onSaved?.(saved);
    } catch (e) {
      setError(saveFailure(e, draft.id));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <FormDialog
        open={open}
        onOpenChange={onOpenChange}
        title={goal ? `Edit “${goal.title}”` : "New goal"}
        submitLabel={editing ? "Save" : "Create goal"}
        busy={busy}
        error={error}
        canSubmit={!idError}
        onSubmit={save}
        extraActions={
          goal ? (
            <Button variant="ghost" icon="trash" onClick={() => setDeleting(true)}>
              Delete
            </Button>
          ) : undefined
        }
      >
        <TextField
          label="Name"
          value={draft.title}
          autoFocus
          placeholder="Deliver the Ember Seal"
          onChange={(title) => setDraft((d) => withTitle(d, title))}
        />
        <TextField
          label="Id"
          mono
          value={draft.id}
          disabled={editing}
          placeholder="deliver-the-ember-seal"
          error={draft.id || draft.title ? idError : null}
          hint={
            editing
              ? "An id is permanent — it is what threads and other goals point at."
              : "Derived from the name; edit it before creating if you want another."
          }
          onChange={(id) => setDraft((d) => withId(d, id))}
        />
        <TextAreaField
          label="What it is"
          rows={3}
          value={draft.description}
          placeholder="What this goal is, in your own words."
          onChange={(description) => setDraft((d) => ({ ...d, description }))}
        />
        <Prerequisites
          draft={draft}
          goals={goals}
          onChange={(dependsOn) => setDraft((d) => ({ ...d, dependsOn }))}
        />
        <DeliveringScene
          book={book}
          draft={draft}
          onChange={(scene) =>
            setDraft((d) => ({
              ...d,
              achievedAt: scene?.id ?? null,
              achievedTitle: scene?.title ?? null,
            }))
          }
        />
      </FormDialog>
      {goal ? (
        <DeleteGoalDialog
          book={book}
          goal={goal}
          open={deleting}
          onOpenChange={setDeleting}
          onDeleted={() => onOpenChange(false)}
        />
      ) : null}
    </>
  );
}
