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

import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import type { EventSummary, Plotline } from "../../api/types";
import { useRoute } from "../../hooks/useRoute";
import { useRefreshBook } from "../../hooks/mutations";
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
import { Button } from "../../../components/ui/Button";
import { Modal } from "../../../components/ui/Modal";
import { InspectorPeek } from "../../components/inspector/Inspector";
import { Skeleton } from "../../../components/ui/Skeleton";
import { ConfirmDialog } from "../../components/form/ConfirmDialog";
import { sceneElement } from "../../views/plotline/useJump";
import { useFocusMode } from "../../views/plotline/useFocusMode";
import { focusLabel } from "../../logic/plotline/focus";
import { conflictCount } from "../../logic/plotline/verdicts";
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

/**
 * Flash a row the writer was pointed at, or, when the scene is not in this
 * order, peek at it over the editor: the inspector beside the page is out of
 * reach while the dialog is open.
 */
function useEditorJump(root: HTMLElement | null) {
  const [peek, setPeek] = useState<string | null>(null);
  const jump = (scene: string) => {
    const target = sceneElement(root, scene);
    if (!target) return setPeek(scene);
    target.scrollIntoView({ block: "center", behavior: "smooth" });
    target.classList.add("is-flash");
    setTimeout(() => target.classList.remove("is-flash"), 1200);
  };
  const peeking = peek ? (
    <InspectorPeek target={{ kind: "scene", id: peek }} onClose={() => setPeek(null)} />
  ) : null;
  return { jump, peeking };
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

/** Whether closing now would lose edits; the body keeps it current. */
type Unsaved = MutableRefObject<() => boolean>;

function EditorBody({
  creating,
  loaded: current,
  onClose,
  onCancel,
  onReload,
  unsavedRef,
}: {
  creating: boolean;
  loaded: Loaded;
  /** Done: saved or deleted. */
  onClose: () => void;
  /** Leave without saving, asking first if there is anything to lose. */
  onCancel: () => void;
  onReload: () => void;
  unsavedRef: Unsaved;
}) {
  const { id: book, book: record, calendar } = useBookScope();
  const { list: threads } = useThreads(book);
  const { go } = useRoute();
  const refresh = useRefreshBook();
  const { editScene, newScene } = useActions();
  // The thread as it was opened, kept for the whole session: Save sends its
  // revision, so a refetch while the draft is open -- the tab regaining focus,
  // a scene saved from a row -- cannot let the draft overwrite a newer save.
  // "Reload their version" starts a new session from the server's copy.
  const [loaded] = useState(current);
  const draftControls = useThreadDraft(loaded.draft);
  const { editing, edit, update } = draftControls;
  const { draft, alternative } = editing;
  const [idTakenOver, setIdTakenOver] = useState(!creating);
  const [picked, setPicked] = useState<EventSummary[]>([]);
  // Bumped when something outside the draft changes a verdict: a new ending.
  const [recheck, setRecheck] = useState(0);
  const [confirm, setConfirm] = useState<"delete" | { ending: OrderRow } | null>(null);
  const [root, setRoot] = useState<HTMLDivElement | null>(null);
  // The thread screen's focus mode, remembered with it: the marks go, the order stays.
  const [hideMarks, toggleMarks] = useFocusMode();
  const writes = useThreadWrites(book, creating, loaded.rev);
  useHistoryKeys(draftControls.undo, draftControls.redo, root);
  const { canUndo } = draftControls;
  useEffect(() => {
    unsavedRef.current = () => canUndo;
  }, [unsavedRef, canUndo]);

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

  const { jump, peeking } = useEditorJump(root);
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
      void refresh(book);
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
    <div ref={setRoot} className={`cw-editor${hideMarks ? " is-focus" : ""}`}>
      <DraftToolbar
        canUndo={draftControls.canUndo}
        canRedo={draftControls.canRedo}
        onUndo={draftControls.undo}
        onRedo={draftControls.redo}
        comparing={alternative !== null}
        canCompare={draft.events.length > 0}
        onStartComparing={() => update(startComparing)}
        onStopComparing={() => update((e) => keep(e, "A"))}
        focusLabel={focusLabel(hideMarks, conflictCount(previewA.current?.status))}
        onFocus={toggleMarks}
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
        onCancel={onCancel}
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
      {peeking}
    </div>
  );
}

function ExistingThread({
  id,
  onClose,
  onCancel,
  unsavedRef,
}: {
  id: string;
  onClose: () => void;
  onCancel: () => void;
  unsavedRef: Unsaved;
}) {
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
      onCancel={onCancel}
      onReload={reload}
      unsavedRef={unsavedRef}
    />
  );
}

/**
 * The editor in its dialog: `id` null writes a new thread. A draft can be a
 * long rearrangement, so Escape, a click outside or Cancel asks before
 * throwing one away.
 */
export function ThreadEditor({ id, onClose }: { id: string | null; onClose: () => void }) {
  const unsavedRef = useRef<() => boolean>(() => false);
  const [asking, setAsking] = useState(false);
  const cancel = () => (unsavedRef.current() ? setAsking(true) : onClose());
  return (
    <>
      <Modal
        open
        onOpenChange={(open) => !open && cancel()}
        title={id ? "Edit thread" : "New thread"}
        description="Arrange the scenes; Chronos checks the order as you go."
        wide
        className="cw-thread-editor"
      >
        {id ? (
          <ExistingThread
            id={id}
            onClose={onClose}
            onCancel={cancel}
            unsavedRef={unsavedRef}
          />
        ) : (
          <EditorBody
            creating
            loaded={{ draft: emptyDraft(), rev: null, scenes: [] }}
            onClose={onClose}
            onCancel={cancel}
            onReload={onClose}
            unsavedRef={unsavedRef}
          />
        )}
      </Modal>
      <ConfirmDialog
        open={asking}
        onOpenChange={setAsking}
        title="Discard your changes?"
        confirmLabel="Discard changes"
        onConfirm={onClose}
      >
        <p>Nothing has been saved. Closing the editor throws this draft away.</p>
      </ConfirmDialog>
    </>
  );
}
