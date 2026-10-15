// The scene editor: write a new scene, or correct an existing one's timing,
// place and cast without leaving what you were reading. A mis-timed scene is
// the commonest cause of a conflict, so it has to be fixable from wherever the
// conflict is shown -- the Issues triage, the inspector, a thread.
//
// An existing scene is read afresh when the editor opens, so the revision the
// save sends is the scene as it is now, not as some list last saw it.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { EntityRef, EventWrite, SceneEvent } from "../../api/types";
import { ChronosApiError, codeOf, messageOf } from "../../api/errors";
import { useApi } from "../../deps";
import { useRefreshBook } from "../../hooks/mutations";
import { keys } from "../../hooks/queries";
import { followTitle } from "../../logic/ids";
import { createAtFreeId } from "../../logic/scenes/deletion";
import { ROLE_COLLECTION } from "../../logic/scenes/refs";
import { slugify } from "../../logic/text";
import { FormDialog } from "../../components/form/FormDialog";
import { TextAreaField, TextField } from "../../components/form/Fields";
import { QueryState } from "../../components/common/QueryState";
import { useBookScope } from "../../components/shell/BookScope";
import { useNotify } from "../../../components/ui/Toaster";
import { Modal } from "../../../components/ui/Modal";
import { RefField } from "./RefField";
import { TimingField } from "./TimingField";
import { useTiming } from "./useTiming";

// A scene is created *at* an id, so it cannot refuse an empty one the way a book does.
const FALLBACK_SCENE_ID = "scene";

/** Which collections this book's world keeps, and whether it has a world to search at all. */
function useEntityScope(book: string, world: string | null | undefined) {
  const api = useApi();
  const { data } = useQuery({
    queryKey: ["entity-scope", book],
    queryFn: () =>
      api.searchEntities(book, { q: "", collection: ROLE_COLLECTION.characters }),
    staleTime: 5 * 60_000,
  });
  const observed = data?.collections ?? Object.values(ROLE_COLLECTION);
  return { observed, nowhereToSearch: Boolean(data) && !world && observed.length === 0 };
}

/** Why a save failed, in words that say what to do next. */
export function saveProblem(error: unknown): string {
  if (
    error instanceof ChronosApiError &&
    error.isConflict &&
    codeOf(error) !== "ALREADY_EXISTS"
  ) {
    return "This scene changed elsewhere since you opened it — close the editor, reopen the scene and try again.";
  }
  return messageOf(error, "Could not save the scene.");
}

interface Draft {
  title: string;
  id: string;
  idTouched: boolean;
  location: EntityRef[];
  characters: EntityRef[];
  items: EntityRef[];
  description: string;
}

const draftOf = (event: SceneEvent | null): Draft => ({
  title: event?.title ?? "",
  id: event?.id ?? "",
  idTouched: event !== null,
  location: event ? [event.location] : [],
  characters: event?.characters ?? [],
  items: event?.items ?? [],
  description: event?.description ?? "",
});

function SceneForm({
  event,
  onClose,
  onSaved,
}: {
  event: SceneEvent | null;
  onClose: () => void;
  onSaved?: (scene: SceneEvent) => void;
}) {
  const api = useApi();
  const { id: book, book: record, calendar, calendars } = useBookScope();
  const refresh = useRefreshBook();
  const notify = useNotify();
  const scope = useEntityScope(book, record?.world);
  const timing = useTiming(book, calendars, calendar, event);
  const [draft, setDraft] = useState(() => draftOf(event));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const editing = event !== null;
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));

  const save = async () => {
    const place = draft.location[0];
    if (!place) return setError("Choose where this scene happens.");
    const when = timing.timeframe();
    if ("error" in when) return setError(when.error);
    // Nulls in the timeframe say "unscheduled": a PUT replaces, so silence would keep old ticks.
    const body: EventWrite = {
      title: draft.title.trim() || null,
      location: place,
      ...when.body,
      description: draft.description,
      characters: draft.characters,
      items: draft.items,
    };
    const options = { calendar: when.calendar ?? null };
    setBusy(true);
    setError(null);
    try {
      const saved = editing
        ? await api.updateEvent(book, event.id, body, event.rev, options)
        : await createAtFreeId(
            draft.id.trim() || slugify(draft.title) || FALLBACK_SCENE_ID,
            (id) => api.createEvent(book, id, body, options),
            (e) => codeOf(e) === "ALREADY_EXISTS",
          );
      notify({ title: `${editing ? "Saved" : "Created"} “${saved.title || saved.id}”.` });
      void refresh(book);
      onClose();
      onSaved?.(saved);
    } catch (e) {
      setBusy(false);
      setError(saveProblem(e));
    }
  };

  return (
    <FormDialog
      open
      wide
      onOpenChange={(open) => !open && onClose()}
      title={editing ? `Edit “${event.title || event.id}”` : "Write a new scene"}
      submitLabel={editing ? "Save scene" : "Create scene"}
      busy={busy}
      error={error}
      onSubmit={() => void save()}
    >
      <div className="cw-form-row">
        <TextField
          label="Title"
          value={draft.title}
          placeholder="The Harbor Exchange"
          autoFocus={!editing}
          hint="What you will recognise it by on the timeline."
          onChange={(title) =>
            set({ title, id: followTitle(title, draft.id, draft.idTouched) })
          }
        />
        <TextField
          label="Id"
          mono
          value={draft.id}
          placeholder="harbor-exchange"
          disabled={editing}
          hint={
            editing
              ? "A scene's id is permanent."
              : "Used in links and in the API. Follows the title until you change it."
          }
          onChange={(id) => set({ id, idTouched: true })}
        />
      </div>
      <RefField
        book={book}
        role="location"
        label="Place"
        hint="Where the scene happens. Required."
        multiple={false}
        value={draft.location}
        onChange={(location) => set({ location })}
        observed={scope.observed}
        nowhereToSearch={scope.nowhereToSearch}
      />
      <TimingField timing={timing} />
      <div className="cw-form-row">
        <RefField
          book={book}
          role="characters"
          label="Characters"
          hint="Who is present. Two scenes sharing a character at different places at overlapping times are a conflict."
          multiple
          value={draft.characters}
          onChange={(characters) => set({ characters })}
          observed={scope.observed}
          nowhereToSearch={scope.nowhereToSearch}
        />
        <RefField
          book={book}
          role="items"
          label="Items"
          multiple
          value={draft.items}
          onChange={(items) => set({ items })}
          observed={scope.observed}
          nowhereToSearch={scope.nowhereToSearch}
        />
      </div>
      <TextAreaField
        label="What happens"
        value={draft.description}
        rows={4}
        placeholder="What happens here (optional)"
        onChange={(description) => set({ description })}
      />
    </FormDialog>
  );
}

/** Edit: read the scene first, so the save carries its current revision. */
function EditScene({
  id,
  onClose,
  onSaved,
}: {
  id: string;
  onClose: () => void;
  onSaved?: (scene: SceneEvent) => void;
}) {
  const api = useApi();
  const { id: book, calendar } = useBookScope();
  const query = useQuery({
    queryKey: keys.event(book, id, calendar),
    queryFn: () => api.getEvent(book, id, { calendar }),
    refetchOnMount: "always",
  });
  if (query.data && !query.isFetching)
    return <SceneForm event={query.data} onClose={onClose} onSaved={onSaved} />;
  return (
    <Modal open onOpenChange={(open) => !open && onClose()} title="Opening the scene…">
      <QueryState query={{ ...query, data: undefined }}>{() => null}</QueryState>
    </Modal>
  );
}

export function SceneEditor({
  sceneId,
  onClose,
  onSaved,
}: {
  sceneId: string | null;
  onClose: () => void;
  /** Told about the scene once it is saved. */
  onSaved?: (scene: SceneEvent) => void;
}) {
  return sceneId === null ? (
    <SceneForm event={null} onClose={onClose} onSaved={onSaved} />
  ) : (
    <EditScene id={sceneId} onClose={onClose} onSaved={onSaved} />
  );
}
