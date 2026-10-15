// The thread editor's furniture, drawn from what the editor holds: the draft
// toolbar, the thread's own fields, the footer and the questions it asks
// before anything irreversible. None of them keeps state; the editor does.

import { continueInto, type ThreadDraft } from "../../logic/plotline/draft";
import type { OrderRow } from "../../logic/plotline/rows";
import { ConfirmDialog } from "../../components/form/ConfirmDialog";
import { TextAreaField, TextField } from "../../components/form/Fields";
import { Button, IconButton } from "../../../components/ui/Button";
import { ContinuationField, GoalsField } from "./Pickers";

export function DraftToolbar({
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  comparing,
  canCompare,
  onStartComparing,
  onStopComparing,
  focusLabel,
  onFocus,
}: {
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  comparing: boolean;
  canCompare: boolean;
  onStartComparing: () => void;
  onStopComparing: () => void;
  /** "Hide problems", or what showing them again would show. */
  focusLabel: string;
  onFocus: () => void;
}) {
  return (
    <div className="cw-editor-toolbar" role="toolbar" aria-label="Draft">
      <IconButton icon="undo" label="Undo (⌘Z)" disabled={!canUndo} onClick={onUndo} />
      <IconButton icon="redo" label="Redo (⇧⌘Z)" disabled={!canRedo} onClick={onRedo} />
      <span className="cw-editor-toolbar-gap" />
      <Button
        size="sm"
        variant="ghost"
        icon="eye"
        title="Continuity marks stay computed either way — this only hides them."
        onClick={onFocus}
      >
        {focusLabel}
      </Button>
      {comparing ? (
        <Button size="sm" variant="ghost" icon="x" onClick={onStopComparing}>
          Stop comparing
        </Button>
      ) : (
        <Button size="sm" icon="compare" disabled={!canCompare} onClick={onStartComparing}>
          Compare an alternative
        </Button>
      )}
    </div>
  );
}

export type ThreadTextField = "title" | "id" | "overview";

export function ThreadFields({
  draft,
  creating,
  onText,
  onDraft,
}: {
  draft: ThreadDraft;
  creating: boolean;
  onText: (field: ThreadTextField, value: string) => void;
  /** A change to anything but the text fields, as the whole next draft. */
  onDraft: (next: ThreadDraft) => void;
}) {
  return (
    <div className="cw-editor-fields">
      <TextField
        label="Name"
        value={draft.title}
        placeholder={draft.id || "The Knight's Road"}
        autoFocus={creating}
        onChange={(v) => onText("title", v)}
      />
      <TextField
        label="Id"
        mono
        value={draft.id}
        disabled={!creating}
        hint={
          creating
            ? "Used in links. Follows the name until you change it."
            : "A thread's id is permanent."
        }
        onChange={(v) => onText("id", v)}
      />
      <div className="cw-editor-wide">
        <TextAreaField
          label="Overview"
          rows={2}
          value={draft.overview}
          placeholder="What this thread is about (optional)"
          hint="A note to yourself. No rule reads it, so it changes no verdict."
          onChange={(v) => onText("overview", v)}
        />
      </div>
      <GoalsField value={draft.goals} onChange={(goals) => onDraft({ ...draft, goals })} />
      <div>
        <ContinuationField
          self={draft.id}
          target={draft.continuesInto}
          title={draft.continuesIntoTitle}
          joinAt={draft.continuesIntoAt}
          onTarget={(id, title) => onDraft(continueInto(draft, id, title))}
          onJoinAt={(at) => onDraft({ ...draft, continuesIntoAt: at })}
        />
      </div>
    </div>
  );
}

/** The line beside Save: why it is disabled, or what saving will and will not do. */
export function footNote(
  comparing: boolean,
  problems: string[],
  creating: boolean,
): string {
  if (comparing) return "Keep A or B to save.";
  if (problems[0]) return problems[0];
  return creating
    ? "Nothing is written until you create it."
    : "Findings never block a save.";
}

export function EditorFooter({
  creating,
  canDelete,
  comparing,
  problems,
  busy,
  onDelete,
  onCancel,
  onSave,
}: {
  creating: boolean;
  canDelete: boolean;
  comparing: boolean;
  problems: string[];
  busy: boolean;
  onDelete: () => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  return (
    <div className="cw-editor-foot">
      {!creating && canDelete ? (
        <Button
          variant="ghost"
          className="cw-editor-delete"
          icon="trash"
          onClick={onDelete}
        >
          Delete thread
        </Button>
      ) : null}
      <span className="cw-editor-foot-note">{footNote(comparing, problems, creating)}</span>
      <Button variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
      <Button
        variant="primary"
        busy={busy}
        disabled={problems.length > 0 || comparing}
        onClick={onSave}
      >
        {creating ? "Create thread" : "Save changes"}
      </Button>
    </div>
  );
}

export function ConfirmDelete({
  open,
  title,
  busy,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => !next && onCancel()}
      title={`Delete “${title}”?`}
      confirmLabel="Delete"
      busy={busy}
      onConfirm={onConfirm}
    >
      <p>The scenes stay in the book; only this thread through them goes away.</p>
    </ConfirmDialog>
  );
}

/** The server refused the delete: other threads continue into this one. */
export function ConfirmAbsorb({
  dependents,
  busy,
  onCancel,
  onConfirm,
}: {
  /** The continuing threads' titles; null while there is nothing to ask. */
  dependents: string[] | null;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <ConfirmDialog
      open={dependents !== null}
      onOpenChange={(next) => !next && onCancel()}
      title="Other threads continue into this one"
      confirmLabel="Copy in and delete"
      busy={busy}
      onConfirm={onConfirm}
    >
      <p>These threads would lose the rest of their story:</p>
      <div className="cw-chip-row">
        {(dependents ?? []).map((title) => (
          <span key={title} className="cw-chip cw-chip-thread">
            {title}
          </span>
        ))}
      </div>
      <p>
        Copy this thread's scenes into each of them first, so they keep the story they have?
      </p>
    </ConfirmDialog>
  );
}

export function ConfirmEnding({
  ending,
  current,
  busy,
  onCancel,
  onConfirm,
}: {
  /** The scene about to become the ending; null while there is nothing to ask. */
  ending: OrderRow | null;
  /** What the current ending is called. */
  current: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (row: OrderRow) => void;
}) {
  return (
    <ConfirmDialog
      open={ending !== null}
      onOpenChange={(next) => !next && onCancel()}
      title="Change the book's ending?"
      confirmLabel="Make it the ending"
      danger={false}
      busy={busy}
      onConfirm={() => ending && onConfirm(ending)}
    >
      <p>“{current}” is the scene every thread is currently expected to reach.</p>
      <p>
        Make “{ending?.title ?? ""}” the ending instead? Every thread is re-checked against
        it, and this writes straight away.
      </p>
    </ConfirmDialog>
  );
}
