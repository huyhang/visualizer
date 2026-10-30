// Choosing the Chronos scenes a section tells: every scene in the book, in
// story order, ticked where the section names it now.

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { messageOf } from "../../api/errors";
import { Button } from "../../../components/ui/Button";
import { Modal } from "../../../components/ui/Modal";
import { useDeps } from "../../deps";
import { chosenOrder } from "../../logic/scenes";

export function SceneDialog({
  book,
  name,
  current,
  onSave,
  onClose,
}: {
  book: string;
  /** What the section is called, for the heading. */
  name: string;
  current: string[];
  /** Resolves once saved; throws to say why not. */
  onSave: (eventIds: string[]) => Promise<void>;
  onClose: () => void;
}) {
  const { api } = useDeps();
  const choices = useQuery({
    queryKey: ["scene-choices", book],
    queryFn: () => api.sceneChoices(book),
  });
  const [picked, setPicked] = useState(() => new Set(current));
  const [filter, setFilter] = useState("");
  const [state, setState] = useState<{ busy: boolean; error: string | null }>({
    busy: false,
    error: null,
  });

  const all = useMemo(() => choices.data ?? [], [choices.data]);
  // A scene the section names that Chronos no longer has is still listed, so
  // it can be let go.
  const rows = useMemo(() => {
    const known = new Set(all.map((choice) => choice.id));
    const gone = current
      .filter((id) => !known.has(id))
      .map((id) => ({ id, title: id, when: "", missing: true }));
    const needle = filter.trim().toLocaleLowerCase();
    return [...gone, ...all].filter(
      (row) => !needle || row.title.toLocaleLowerCase().includes(needle),
    );
  }, [all, current, filter]);

  const toggle = (id: string) =>
    setPicked((before) => {
      const next = new Set(before);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const save = async () => {
    setState({ busy: true, error: null });
    try {
      await onSave(chosenOrder(current, picked, all));
      onClose();
    } catch (error) {
      setState({ busy: false, error: messageOf(error, "The scenes were not saved.") });
    }
  };

  const unchanged = picked.size === current.length && current.every((id) => picked.has(id));

  return (
    <Modal
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Scenes in ${name}`}
      description="The Chronos scenes this section tells. They show above the page, and in the reader's Full view."
      className="lw-dialog lw-scene-dialog"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            busy={state.busy}
            disabled={!choices.isSuccess || unchanged}
            onClick={() => void save()}
          >
            Save
          </Button>
        </>
      }
    >
      {choices.isLoading ? (
        <p className="lw-muted">Loading the book's scenes…</p>
      ) : choices.isError ? (
        <p className="st-error-text" role="alert">
          {messageOf(choices.error, "The book's scenes could not be loaded.")}
        </p>
      ) : !all.length && !current.length ? (
        <p className="lw-muted">
          This book has no scenes in Chronos yet. Add them on its timeline, then come back
          to link them.
        </p>
      ) : (
        <>
          <input
            className="st-input st-input-sm lw-scene-filter"
            type="search"
            placeholder="Filter scenes"
            aria-label="Filter scenes"
            value={filter}
            autoFocus
            onChange={(event) => setFilter(event.target.value)}
          />
          <ul className="lw-scene-choices">
            {rows.map((row) => (
              <li key={row.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={picked.has(row.id)}
                    onChange={() => toggle(row.id)}
                  />
                  <span className="lw-scene-choice-title">{row.title}</span>
                  <span className="lw-scene-choice-when">
                    {row.missing ? "No longer in Chronos" : row.when}
                  </span>
                </label>
              </li>
            ))}
            {!rows.length ? <li className="lw-muted">No scene matches.</li> : null}
          </ul>
        </>
      )}
      {state.error ? (
        <p className="st-error-text" role="alert">
          {state.error}
        </p>
      ) : null}
    </Modal>
  );
}
