// The thread editor: write a new thread, or change an existing one's name,
// goals, continuation and -- the point of the exercise -- the order of its scenes.
//
// Three decisions shape it, all carried over from the classic editor:
// * Edit mode, saved explicitly. Dragging is a draft; one save commits it,
//   carrying the revision, so a save that would clobber someone else's edit is
//   refused rather than winning. Cancel costs nothing, and undo walks back.
// * The server judges the draft. After every change the candidate goes to the
//   preview endpoint, so conflicts appear while you drag and no story rule is
//   reimplemented here.
// * Only your own scenes move. Inherited ones are shown, locked.
//
// And one that is new: an alternative order can be tried beside the current
// one, each judged on its own, before either is kept.

import { useMemo, useState } from "react";
import type { EventSummary, Plotline } from "../../api/types";
import { useRoute } from "../../hooks/useRoute";
import { usePlotline } from "../../hooks/queries";
import { useThreads } from "../../hooks/useThreads";
import { followTitle } from "../../logic/ids";
import { movedPositions } from "../../logic/plotline/compare";
import {
  candidateKey,
  candidateOf,
  draftFrom,
  draftProblems,
  emptyDraft,
  type ThreadDraft,
} from "../../logic/plotline/draft";
import {
  addScene,
  keep,
  moveScene,
  removeScene,
  startComparing,
  withOrder,
  type Side,
} from "../../logic/plotline/editing";
import { remember, type OrderRow } from "../../logic/plotline/rows";
import { to } from "../../logic/route";
import { useActions } from "../../components/shell/Actions";
import { useBookScope } from "../../components/shell/BookScope";
import { useInspector } from "../../components/shell/InspectorContext";
import { Button } from "../../../components/ui/Button";
import { Modal } from "../../../components/ui/Modal";
import { Skeleton } from "../../../components/ui/Skeleton";
import { sceneElement } from "../../views/plotline/useJump";
import { CompareBar } from "./Compare";
import { OrderColumn } from "./OrderColumn";
import {
  ConfirmAbsorb,
  ConfirmDelete,
  ConfirmEnding,
  DraftToolbar,
  EditorFooter,
  ThreadFields,
  type ThreadTextField,
} from "./EditorParts";
import { summaryOfScene } from "./Pickers";
import { useHistoryKeys, useThreadDraft } from "./useThreadDraft";
import { usePreview } from "./usePreview";
import { useThreadWrites, type Refusal } from "./useThreadWrites";

interface Loaded {
  draft: ThreadDraft;
  rev: number | null;
  /** The scenes the thread was opened with, so rows read as titles before the first verdict. */
  scenes: EventSummary[];
}

function loadedFrom(plotline: Plotline): Loaded {
  return {
    draft: draftFrom(plotline),
    rev: plotline.rev,
    scenes: plotline.effective_events.filter(
      (e): e is EventSummary => typeof e !== "string",
    ),
  };
}

/** Flash a row the writer was pointed at, or open the scene beside the editor when it is not here. */
function useEditorJump(root: HTMLElement | null) {
  const inspector = useInspector();
  return (scene: string) => {
    const target = sceneElement(root, scene);
    if (!target) return inspector.open({ kind: "scene", id: scene });
    target.scrollIntoView({ block: "center", behavior: "smooth" });
    target.classList.add("is-flash");
    setTimeout(() => target.classList.remove("is-flash"), 1200);
  };
}

function RefusalNote({
  refusal,
  onReload,
}: {
  refusal: Refusal | null;
  onReload: () => void;
}) {
  if (!refusal || refusal.kind === "in-use") return null;
  if (refusal.kind === "stale") {
    return (
      <div className="cw-form-error" role="alert">
        Someone else changed this thread since you opened it, so saving would overwrite
        their work.{" "}
        <Button size="sm" variant="secondary" onClick={onReload}>
          Reload their version
        </Button>
      </div>
    );
  }
  return (
    <p className="cw-form-error" role="alert">
      {refusal.text}
    </p>
  );
}

function EditorBody({
  creating,
  loaded,
  onClose,
  onReload,
}: {
  creating: boolean;
  loaded: Loaded;
  onClose: () => void;
  onReload: () => void;
}) {
  const { id: book, book: record, calendar } = useBookScope();
  const { list: threads } = useThreads(book);
  const { go } = useRoute();
  const { editScene, newScene } = useActions();
  const draftControls = useThreadDraft(loaded.draft);
  const { editing, edit, update } = draftControls;
  const { draft, alternative } = editing;
  const [idTakenOver, setIdTakenOver] = useState(!creating);
  const [picked, setPicked] = useState<EventSummary[]>([]);
  // Bumped when something outside the draft changes a verdict: a new ending.
  const [recheck, setRecheck] = useState(0);
  const [confirm, setConfirm] = useState<"delete" | { ending: OrderRow } | null>(null);
  const [root, setRoot] = useState<HTMLDivElement | null>(null);
  const writes = useThreadWrites(book, creating, loaded.rev);
  useHistoryKeys(draftControls.undo, draftControls.redo);

  const previewA = usePreview(
    book,
    candidateOf(draft),
    `${candidateKey(draft)}#${recheck}`,
    calendar,
  );
  const previewB = usePreview(
    book,
    candidateOf(draft, alternative ?? []),
    alternative ? `${candidateKey(draft, alternative)}#${recheck}` : "none",
    calendar,
  );
  const known = useMemo(
    () =>
      remember(new Map(), [
        ...loaded.scenes,
        ...picked,
        ...(previewA.last?.effective_events ?? []),
        ...(previewB.last?.effective_events ?? []),
      ]),
    [loaded.scenes, picked, previewA.last, previewB.last],
  );

  const jump = useEditorJump(root);
  const terminus = record?.terminus ?? null;
  const problems = draftProblems(
    draft,
    creating,
    threads.map((t) => t.id),
  );
  const continuationTitle = draft.continuesIntoTitle ?? draft.continuesInto;

  const setField = (field: ThreadTextField, value: string) => {
    const next = { ...draft, [field]: value };
    if (field === "title" && creating) next.id = followTitle(value, draft.id, idTakenOver);
    if (field === "id") setIdTakenOver(true);
    edit({ ...editing, draft: next }, field);
  };

  const save = async () => {
    const saved = await writes.save(draft);
    if (!saved) return;
    onClose();
    if (creating) go(to.plotline(book, saved.id));
  };
  const remove = async (inline: boolean) => {
    if (await writes.remove(draft.id, inline)) {
      onClose();
      go(to.threads(book));
    } else setConfirm(null);
  };
  const makeEnding = async (row: OrderRow) => {
    setConfirm(null);
    if (await writes.makeEnding(row.id, row.title)) setRecheck((n) => n + 1);
  };

  const column = (side: Side) => {
    const order = side === "A" ? draft.events : (alternative ?? []);
    return (
      <OrderColumn
        book={book}
        label={
          side === "A" ? (alternative ? "Current order" : "Scenes") : "Alternative order"
        }
        order={order}
        preview={side === "A" ? previewA : previewB}
        known={known}
        terminus={terminus}
        continuationTitle={continuationTitle}
        moved={
          side === "B" && alternative
            ? movedPositions(draft.events, alternative)
            : undefined
        }
        onOrder={(next) => update((e) => withOrder(e, side, next))}
        onMove={(from, to_) => update((e) => moveScene(e, side, from, to_))}
        onRemove={(index) => update((e) => removeScene(e, side, index))}
        onAdd={(scene, at) => {
          setPicked((all) => [...all, scene]);
          update((e) => addScene(e, side, scene.id, at));
        }}
        onMakeEnding={(row) =>
          terminus ? setConfirm({ ending: row }) : void makeEnding(row)
        }
        onEditScene={
          editScene
            ? (id) => editScene(id, { onSaved: () => setRecheck((n) => n + 1) })
            : undefined
        }
        onWriteNew={
          newScene
            ? (at) =>
                newScene({
                  onSaved: (scene) => {
                    const added = summaryOfScene(scene);
                    setPicked((all) => [...all, added]);
                    update((e) => addScene(e, side, added.id, at));
                  },
                })
            : undefined
        }
        onJump={jump}
      />
    );
  };

  const ending = typeof confirm === "object" ? (confirm?.ending ?? null) : null;
  const dependents =
    writes.refusal?.kind === "in-use"
      ? writes.refusal.dependents.map((id) => threads.find((t) => t.id === id)?.title ?? id)
      : null;

  return (
    <div ref={setRoot} className="cw-editor">
      <DraftToolbar
        canUndo={draftControls.canUndo}
        canRedo={draftControls.canRedo}
        onUndo={draftControls.undo}
        onRedo={draftControls.redo}
        comparing={alternative !== null}
        canCompare={draft.events.length > 0}
        onStartComparing={() => update(startComparing)}
        onStopComparing={() => update((e) => keep(e, "A"))}
      />
      <ThreadFields
        draft={draft}
        creating={creating}
        onText={setField}
        onDraft={(next) => edit({ ...editing, draft: next })}
      />

      {alternative ? (
        <>
          <CompareBar
            a={previewA.current}
            b={previewB.current}
            onKeep={(side) => update((e) => keep(e, side))}
          />
          <div className="cw-editor-columns">
            {column("A")}
            {column("B")}
          </div>
        </>
      ) : (
        column("A")
      )}

      <RefusalNote refusal={writes.refusal} onReload={onReload} />
      <EditorFooter
        creating={creating}
        canDelete={record?.permissions?.delete ?? false}
        comparing={alternative !== null}
        problems={problems}
        busy={writes.busy}
        onDelete={() => setConfirm("delete")}
        onCancel={onClose}
        onSave={save}
      />

      <ConfirmDelete
        open={confirm === "delete"}
        title={draft.title || draft.id}
        busy={writes.busy}
        onCancel={() => setConfirm(null)}
        onConfirm={() => remove(false)}
      />
      <ConfirmAbsorb
        dependents={dependents}
        busy={writes.busy}
        onCancel={writes.clearRefusal}
        onConfirm={() => remove(true)}
      />
      <ConfirmEnding
        ending={ending}
        current={known.get(terminus ?? "")?.title ?? terminus ?? ""}
        busy={writes.busy}
        onCancel={() => setConfirm(null)}
        onConfirm={makeEnding}
      />
    </div>
  );
}

function ExistingThread({ id, onClose }: { id: string; onClose: () => void }) {
  const { id: book, calendar } = useBookScope();
  const query = usePlotline(book, id, calendar);
  // A reload is a fresh start from the server's copy: a new session of the body.
  const [session, setSession] = useState(0);
  if (!query.data)
    return query.error ? (
      <p className="cw-form-error">That thread could not be opened.</p>
    ) : (
      <Skeleton lines={6} />
    );
  const reload = async () => {
    await query.refetch();
    setSession((n) => n + 1);
  };
  return (
    <EditorBody
      key={session}
      creating={false}
      loaded={loadedFrom(query.data)}
      onClose={onClose}
      onReload={reload}
    />
  );
}

/** The editor in its dialog: `id` null writes a new thread. */
export function ThreadEditor({ id, onClose }: { id: string | null; onClose: () => void }) {
  return (
    <Modal
      open
      onOpenChange={(open) => !open && onClose()}
      title={id ? "Edit thread" : "New thread"}
      description="Arrange the scenes; Chronos checks the order as you go."
      wide
      className="cw-thread-editor"
    >
      {id ? (
        <ExistingThread id={id} onClose={onClose} />
      ) : (
        <EditorBody
          creating
          loaded={{ draft: emptyDraft(), rev: null, scenes: [] }}
          onClose={onClose}
          onReload={onClose}
        />
      )}
    </Modal>
  );
}
