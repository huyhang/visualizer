// Deleting a scene, the one irreversible act on the Scenes screen.
//
// The browse rows carry no revision, so the scene is read first: one cheap
// request buys a delete that refuses rather than clobbers when someone changed
// the scene since the page was drawn. The server decides and the browser
// explains -- a scene in use, or the book's ending, gets a dialog naming what
// is in the way and the way through, not a toast of server prose.

import { useCallback, useState } from "react";
import type { SceneEvent } from "../../api/types";
import { ChronosApiError, codeOf, evidenceIds, messageOf } from "../../api/errors";
import { useApi } from "../../deps";
import { useRefreshBook } from "../../hooks/mutations";
import {
  afterInUse,
  firstStep,
  type DeleteStep,
  type ThreadInWay,
} from "../../logic/scenes/deletion";
import { Chip } from "../../components/common/Chips";
import { ConfirmDialog } from "../../components/form/ConfirmDialog";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { useNotify } from "../../../components/ui/Toaster";

const sceneName = (event: SceneEvent) => event.title || event.id;

function ThreadList({ threads }: { threads: ThreadInWay[] }) {
  return (
    <div className="cw-chip-row">
      {threads.map((t) => (
        <Chip key={t.id} icon="branch">
          {t.title}
        </Chip>
      ))}
    </div>
  );
}

/** The dialog for one step of a deletion. */
function StepDialog({
  step,
  busy,
  error,
  onClose,
  onDelete,
}: {
  step: DeleteStep;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onDelete: (event: SceneEvent, detach: boolean) => void;
}) {
  const close = (open: boolean) => !open && onClose();
  switch (step.kind) {
    case "idle":
      return null;
    case "confirm":
      return (
        <ConfirmDialog
          open
          onOpenChange={close}
          title={`Delete “${sceneName(step.event)}”?`}
          confirmLabel="Delete"
          busy={busy}
          error={error}
          onConfirm={() => onDelete(step.event, false)}
        >
          <p>
            The scene is removed from the book for good — there is no undo. The characters,
            items and places it references are articles, and are not touched.
          </p>
        </ConfirmDialog>
      );
    case "detach":
      return (
        <ConfirmDialog
          open
          onOpenChange={close}
          title="Other threads use this scene"
          confirmLabel="Take it out of them and delete"
          busy={busy}
          error={error}
          onConfirm={() => onDelete(step.event, true)}
        >
          <p>These threads list it, and will be edited to drop it:</p>
          <ThreadList threads={step.threads} />
          <p>The rest of each thread is left exactly as it is.</p>
        </ConfirmDialog>
      );
    case "would-empty":
      return (
        <ConfirmDialog
          open
          onOpenChange={close}
          title="That would leave a thread with no scenes"
          confirmLabel="Close"
          danger={false}
          onConfirm={onClose}
        >
          <p>“{sceneName(step.event)}” is the only scene in:</p>
          <ThreadList threads={step.emptied} />
          <p>
            A thread needs at least one scene, so dropping this one would leave a thread
            that cannot be saved again. Give each of those threads another scene, or delete
            them, and then delete this scene.
          </p>
        </ConfirmDialog>
      );
    case "terminus":
      return (
        <ConfirmDialog
          open
          onOpenChange={close}
          title="This scene is the book's ending"
          confirmLabel="Close"
          danger={false}
          onConfirm={onClose}
        >
          <p>
            “{sceneName(step.event)}” is the scene every thread in this book is expected to
            reach, so deleting it would leave every thread judged against nothing.
          </p>
          <p>
            Mark another scene as the ending — from a thread, or the book's settings — then
            come back and delete this one.
          </p>
        </ConfirmDialog>
      );
  }
}

/** `start(id)` begins deleting a scene; `element` is whatever dialog that needs. */
export function useSceneDeletion(): {
  start: (id: string) => Promise<void>;
  element: React.ReactNode;
} {
  const api = useApi();
  const { id: book, book: record } = useBookScope();
  const terminus = record?.terminus;
  const refresh = useRefreshBook();
  const notify = useNotify();
  const inspector = useInspector();
  const [step, setStep] = useState<DeleteStep>({ kind: "idle" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setStep({ kind: "idle" });
    setError(null);
    setBusy(false);
  }, []);

  const start = useCallback(
    async (id: string) => {
      try {
        const event = await api.getEvent(book, id);
        setError(null);
        setStep(firstStep(event, terminus));
      } catch (e) {
        const gone = e instanceof ChronosApiError && e.isNotFound;
        notify({
          title: gone ? "That scene no longer exists." : "Could not open that scene.",
          tone: "danger",
        });
        void refresh(book);
      }
    },
    [api, book, terminus, notify, refresh],
  );

  // A thread that cannot be read cannot be checked for emptiness; it is still named.
  const threadsInWay = useCallback(
    (ids: string[]) =>
      Promise.all(
        ids.map((id) =>
          api.getPlotline(book, id).then(
            (p): ThreadInWay => ({ id, title: p.title || id, events: p.events }),
            (): ThreadInWay => ({ id, title: id, events: [] }),
          ),
        ),
      ),
    [api, book],
  );

  const remove = useCallback(
    async (event: SceneEvent, detach: boolean) => {
      setBusy(true);
      setError(null);
      try {
        await api.deleteEvent(book, event.id, event.rev, detach);
        notify({ title: `Deleted “${sceneName(event)}”.` });
        // A panel left open on a scene that no longer exists is a confident, wrong answer.
        if (inspector.target?.kind === "scene" && inspector.target.id === event.id)
          inspector.close();
        reset();
        void refresh(book);
      } catch (e) {
        setBusy(false);
        const code = codeOf(e);
        if (code === "EVENT_IN_USE")
          setStep(afterInUse(event, await threadsInWay(evidenceIds(e, "plotlines"))));
        else if (code === "TERMINUS_IN_USE") setStep({ kind: "terminus", event });
        else if (e instanceof ChronosApiError && e.isConflict)
          setError(
            "Something changed while deleting — close this, let the list refresh and try again.",
          );
        else setError(messageOf(e, "Could not delete the scene."));
      }
    },
    [api, book, notify, inspector, reset, refresh, threadsInWay],
  );

  return {
    start,
    element: (
      <StepDialog
        step={step}
        busy={busy}
        error={error}
        onClose={reset}
        onDelete={(event, detach) => void remove(event, detach)}
      />
    ),
  };
}
