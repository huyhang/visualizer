// One note -- an editor's issue or a Coach finding -- with what it says, the
// fix it offers, and what the writer can do about it. The same card sits in
// the popover beside the words and, in full, in the Editor tab.

import type { ReactNode } from "react";
import type { ReviewReference } from "../../api/types";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import {
  noteAnchor,
  noteReplacement,
  type Note,
  type NoteActions,
} from "../../logic/notes";
import { CHECK_LABELS, currentFix, STANCE_LABELS, stanceOf } from "../../logic/review";
import { FixPreview } from "./FixPreview";

export interface NoteCardProps {
  note: Note;
  actions: NoteActions;
  /** Whether the quoted words are still in the draft. */
  placed: boolean;
  references?: ReviewReference[];
  variant: "popover" | "detail";
  /** Shown under the actions -- the discussion, in the Editor tab. */
  children?: ReactNode;
}

function ShowButton({ onShow }: { onShow: () => void }) {
  return (
    <button
      type="button"
      className="st-icon-btn lw-note-show"
      aria-label="Show in the manuscript"
      title="Show in the manuscript"
      onClick={onShow}
    >
      <Icon name="eye" size={15} />
    </button>
  );
}

function Kind({ note }: { note: Note }) {
  if (note.source === "coach") {
    return <span className="lw-kind lw-kind-coach">Coach · {note.issue.category}</span>;
  }
  return (
    <span className={`lw-kind lw-kind-${note.issue.check}`}>
      <span className="lw-kind-dot" aria-hidden="true" />
      {CHECK_LABELS[note.issue.check]}
    </span>
  );
}

function Badges({ note, placed }: { note: Note; placed: boolean }) {
  const badges: ReactNode[] = [];
  if (!placed) {
    badges.push(
      <span
        key="stale"
        className="st-badge"
        title="The quoted words are no longer in this paragraph"
      >
        You changed this passage
      </span>,
    );
  }
  if (note.source === "editor") {
    const { issue } = note;
    if (issue.verified) {
      badges.push(
        <span
          key="verified"
          className="st-badge st-badge-ok"
          title="A second machine confirmed this issue"
        >
          <Icon name="shield" size={12} /> Second-checked
        </span>,
      );
    }
    if (issue.confidence === "likely" && issue.severity === "warning") {
      badges.push(
        <span key="likely" className="st-badge st-badge-warn">
          Likely
        </span>,
      );
    }
    if (issue.dismissed_before) {
      badges.push(
        <span
          key="before"
          className="st-badge"
          title="You dismissed this in an earlier review"
        >
          Dismissed before
        </span>,
      );
    }
    const stance = stanceOf(issue);
    if (stance) {
      badges.push(
        <span key="stance" className={`lw-stance lw-stance-${stance}`}>
          Editor {STANCE_LABELS[stance].toLowerCase()}
        </span>,
      );
    }
  }
  return badges.length ? <div className="lw-badges">{badges}</div> : null;
}

function Fix({ note, placed }: { note: Note; placed: boolean }) {
  const { quote } = noteAnchor(note);
  const replacement = noteReplacement(note);
  const fix = note.source === "editor" ? currentFix(note.issue) : null;
  return (
    <>
      {replacement && placed ? (
        <FixPreview quote={quote} replacement={replacement} />
      ) : (
        <blockquote className="lw-quote">{quote}</blockquote>
      )}
      {fix?.suggestion && fix.suggestion !== replacement ? (
        <p className="lw-suggestion">
          {fix.revised ? <span className="lw-revised">Revised · </span> : null}
          {fix.suggestion}
        </p>
      ) : null}
    </>
  );
}

function Reference({
  note,
  references,
  onOpen,
}: {
  note: Note;
  references?: ReviewReference[];
  onOpen: (ref: string) => void;
}) {
  if (note.source !== "editor" || !note.issue.reference) return null;
  const ref = note.issue.reference;
  const found = references?.find((r) => r.ref === ref);
  return (
    <button
      type="button"
      className="lw-reference"
      onClick={() => onOpen(ref)}
      title={`Open ${ref} in Akasha`}
    >
      <Icon name="book" size={13} />
      <span>Based on {found?.title ?? ref.split("/").at(-1)}</span>
      <Icon name="external" size={12} />
    </button>
  );
}

function Actions({
  note,
  actions,
  placed,
  variant,
}: Pick<NoteCardProps, "note" | "actions" | "placed" | "variant">) {
  const replacement = noteReplacement(note);
  const open = note.source === "coach" || note.issue.status === "open";
  if (!open) {
    return (
      <div className="lw-card-actions">
        <span className="lw-muted lw-small">
          {note.source === "editor" && note.issue.status === "resolved"
            ? "Resolved"
            : "Dismissed"}
        </span>
        <Button size="sm" variant="ghost" onClick={() => actions.reopen(note)}>
          Reopen
        </Button>
      </div>
    );
  }
  return (
    <div className="lw-card-actions">
      {replacement && placed ? (
        <Button
          size="sm"
          variant="primary"
          icon="check"
          onClick={() => actions.accept(note)}
        >
          Accept
        </Button>
      ) : placed ? (
        <Button
          size="sm"
          variant="primary"
          icon="edit"
          onClick={() => actions.editHere(note)}
        >
          Edit here
        </Button>
      ) : note.source === "editor" ? (
        <Button
          size="sm"
          variant="primary"
          icon="check"
          onClick={() => actions.resolve(note)}
        >
          Mark resolved
        </Button>
      ) : null}
      <Button size="sm" variant="secondary" onClick={() => actions.dismiss(note)}>
        Dismiss
      </Button>
      {note.source === "editor" && variant === "popover" ? (
        <Button
          size="sm"
          variant="ghost"
          icon="message"
          onClick={() => actions.discuss(note)}
        >
          Discuss
        </Button>
      ) : null}
      {note.source === "editor" && variant === "detail" && placed && replacement ? (
        <Button
          size="sm"
          variant="ghost"
          icon="edit"
          onClick={() => actions.editHere(note)}
        >
          Edit here
        </Button>
      ) : null}
      {note.source === "coach" ? (
        <button
          type="button"
          className="lw-link-button"
          onClick={() => actions.ignoreRule(note)}
          title="Stop showing this rule"
        >
          Ignore rule
        </button>
      ) : null}
    </div>
  );
}

export function NoteCard({
  note,
  actions,
  placed,
  references,
  variant,
  children,
}: NoteCardProps) {
  const title = note.source === "coach" ? note.issue.title : null;
  return (
    <article
      className={`lw-note lw-note-${variant} lw-note-${note.source} lw-note-k-${note.source === "coach" ? "coach" : note.issue.check}`}
      data-note={note.id}
    >
      <header className="lw-note-head">
        <Kind note={note} />
        <Badges note={note} placed={placed} />
        {variant === "detail" && placed ? (
          <ShowButton onShow={() => actions.show(note)} />
        ) : null}
      </header>
      {title ? <strong className="lw-note-title">{title}</strong> : null}
      <p className="lw-note-message">{note.issue.message}</p>
      <Fix note={note} placed={placed} />
      <Reference note={note} references={references} onOpen={actions.openReference} />
      <Actions note={note} actions={actions} placed={placed} variant={variant} />
      {children}
    </article>
  );
}
