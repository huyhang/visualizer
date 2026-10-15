// The editor's choosers: which goals a thread serves, which thread it
// continues into and where it joins it, and which scene to add. Each picks
// from records the book already has, because the save refuses an id that names
// nothing -- a field that accepts anything and then fails is a worse field.

import { useCallback } from "react";
import type { EventRow, EventSummary, SceneEvent } from "../../api/types";
import { useApi } from "../../deps";
import { useGoals, usePlotline } from "../../hooks/queries";
import { Field } from "../../components/form/Fields";
import { TypeAhead, type Option } from "../../components/form/TypeAhead";
import { Chip } from "../../components/common/Chips";
import { useBookScope } from "../../components/shell/BookScope";
import { Button } from "../../../components/ui/Button";

/** Every word typed appears in the text: the goals are in hand, tens not thousands. */
export const matchesWords = (text: string, query: string) =>
  query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((w) => text.toLowerCase().includes(w));

export function GoalsField({
  value,
  onChange,
}: {
  value: string[];
  onChange: (goals: string[]) => void;
}) {
  const { id: book, calendar } = useBookScope();
  const { data: goals = [] } = useGoals(book, calendar);
  const titleOf = (id: string) => goals.find((g) => g.id === id)?.title ?? id;
  const search = useCallback(
    (q: string): Option<string>[] =>
      goals
        .filter((g) => !value.includes(g.id) && matchesWords(`${g.title} ${g.id}`, q))
        .map((g) => ({ key: g.id, value: g.id, label: g.title, hint: g.id })),
    [goals, value],
  );
  return (
    <Field
      label="Goals"
      hint="What this thread is for. Optional while drafting — the report says which threads serve none."
    >
      {value.length ? (
        <div className="cw-chip-row">
          {value.map((id) => (
            <span key={id} className="cw-removable">
              <Chip tone="ok" icon="target">
                {titleOf(id)}
              </Chip>
              <button
                type="button"
                className="cw-remove"
                aria-label={`Remove ${titleOf(id)}`}
                onClick={() => onChange(value.filter((g) => g !== id))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <TypeAhead
        label="Add a goal"
        placeholder="Add a goal this thread serves…"
        search={search}
        onPick={(id) => onChange([...value, id])}
      />
    </Field>
  );
}

export function ContinuationField({
  self,
  target,
  title,
  joinAt,
  onTarget,
  onJoinAt,
}: {
  self: string;
  target: string | null;
  title: string | null;
  joinAt: string | null;
  onTarget: (id: string | null, title: string | null) => void;
  onJoinAt: (scene: string | null) => void;
}) {
  const api = useApi();
  const { id: book } = useBookScope();
  const search = useCallback(
    async (q: string): Promise<Option<string>[]> => {
      const page = await api.listPlotlines(book, { filter: q, perPage: 20 });
      return page.plotlines
        .filter((p) => p.id !== self)
        .map((p) => ({ key: p.id, value: p.id, label: p.name, hint: p.id }));
    },
    [api, book, self],
  );
  return (
    <>
      <Field
        label="Continues into"
        hint="Carry on into another thread instead of repeating its scenes."
      >
        {target ? (
          <div className="cw-inline-controls">
            <Chip tone="accent" icon="branch" title={target}>
              {title || target}
            </Chip>
            <Button size="sm" variant="ghost" onClick={() => onTarget(null, null)}>
              Clear
            </Button>
          </div>
        ) : (
          <TypeAhead
            label="Continue into a thread"
            placeholder="Ends on its own — search threads to continue into…"
            search={search}
            onPick={(id, o) => onTarget(id, o.label)}
          />
        )}
      </Field>
      {target ? <JoinAtField target={target} value={joinAt} onChange={onJoinAt} /> : null}
    </>
  );
}

/** Where this thread catches the other: everything on its path before that is not inherited. */
function JoinAtField({
  target,
  value,
  onChange,
}: {
  target: string;
  value: string | null;
  onChange: (scene: string | null) => void;
}) {
  const { id: book, calendar } = useBookScope();
  const { data } = usePlotline(book, target, calendar);
  const scenes = (data?.effective_events ?? []).map((e) =>
    typeof e === "string" ? { id: e, title: e } : e,
  );
  return (
    <Field
      label="Joins at"
      hint="Where this thread catches the other one. Everything before it is not inherited."
    >
      <select
        className="st-input"
        aria-label="Joins at"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">At the beginning — inherits the whole thread</option>
        {scenes.map((s) => (
          <option key={s.id} value={s.id}>
            {s.title || s.id}
          </option>
        ))}
      </select>
    </Field>
  );
}

/** A scene row from the book's list, as much of a summary as a row can be drawn from. */
export function summaryOfRow(row: EventRow): EventSummary {
  return {
    id: row.id,
    title: row.title,
    scheduled: row.scheduled,
    start_tick: row.start_tick,
    end_tick: row.end_tick,
    start_label: row.scheduled ? row.when : null,
  };
}

/** A scene just written, as the order draws it until the server's preview names it. */
export function summaryOfScene(scene: SceneEvent): EventSummary {
  return {
    id: scene.id,
    title: scene.title,
    scheduled: scene.scheduled,
    start_tick: scene.start_tick,
    end_tick: scene.end_tick,
    start_label: scene.start_label,
    end_label: scene.end_label,
    location: scene.location,
    characters: scene.characters,
    items: scene.items,
  };
}

export function AddScene({
  label,
  already,
  onAdd,
  onCancel,
  onWriteNew,
  autoFocus,
}: {
  label: string;
  already: string[];
  onAdd: (scene: EventSummary) => void;
  onCancel?: () => void;
  /** Write a scene that does not exist yet; it joins the order once saved. */
  onWriteNew?: () => void;
  autoFocus?: boolean;
}) {
  const api = useApi();
  const { id: book } = useBookScope();
  const search = useCallback(
    async (q: string): Promise<Option<EventRow>[]> => {
      const page = await api.listEvents(book, { filter: q, perPage: 20 });
      return page.events.map((e) => ({
        key: e.id,
        value: e,
        label: e.title,
        hint: `${e.when} · ${e.location}${already.includes(e.id) ? " · already here" : ""}`,
      }));
    },
    [api, book, already],
  );
  return (
    <div className="cw-add-scene">
      <TypeAhead
        label={label}
        placeholder={`${label}: search this book's scenes…`}
        search={search}
        autoFocus={autoFocus}
        onPick={(row) => onAdd(summaryOfRow(row))}
      />
      {onWriteNew ? (
        <Button size="sm" variant="ghost" icon="plus" onClick={onWriteNew}>
          Write a new scene
        </Button>
      ) : null}
      {onCancel ? (
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      ) : null}
    </div>
  );
}
