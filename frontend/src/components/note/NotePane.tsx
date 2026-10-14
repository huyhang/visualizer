import { useState } from "react";
import type { NoteSummary } from "../../api/types";
import {
  problem,
  type Composition,
  type ImageBlock,
  type TextBlock,
} from "../../logic/compose";
import type { DraftActions } from "../draft/actions";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { Spinner } from "../ui/Spinner";
import { NoteBlockView } from "./NoteBlockView";
import { TargetPicker } from "./TargetPicker";

export interface NotePaneProps {
  comp: Composition;
  notes: NoteSummary[];
  loadingNote: boolean;
  saving: boolean;
  saveError: { message: string; conflict: boolean } | null;
  linkTo: DraftActions["linkTo"];
  onTitle: (title: string) => void;
  onNew: () => void;
  onExisting: (slug: string) => void;
  onAddOwn: () => string;
  onChange: (id: string, patch: Partial<TextBlock> | Partial<ImageBlock>) => void;
  onMove: (id: string, delta: number) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
  onSave: () => void;
  onReload: () => void;
}

/** The note being written: where it goes, its title, its blocks, and Save. */
export function NotePane(props: NotePaneProps) {
  const { comp } = props;
  const [fresh, setFresh] = useState<string | null>(null);
  const why = problem(comp);
  const existingTitle = comp.target.kind === "existing" ? comp.title : "";

  return (
    <section className="st-pane st-note" aria-label="Note">
      <div className="st-note-head">
        <TargetPicker
          target={comp.target}
          targetTitle={existingTitle}
          notes={props.notes}
          loading={props.loadingNote}
          onNew={props.onNew}
          onExisting={props.onExisting}
        />
        <input
          className="st-note-title"
          value={comp.title}
          onChange={(e) => props.onTitle(e.target.value)}
          placeholder="Title of the note"
          aria-label="Note title"
          maxLength={300}
        />
      </div>
      <div className="st-scroll st-note-scroll">
        {props.loadingNote ? (
          <div className="st-pad st-center">
            <Spinner label="Opening the note" />
          </div>
        ) : comp.blocks.length ? (
          <ol className="st-blocks">
            {comp.blocks.map((block, n) => (
              <NoteBlockView
                key={block.id}
                block={block}
                first={n === 0}
                last={n === comp.blocks.length - 1}
                startEditing={block.id === fresh}
                linkTo={props.linkTo}
                handlers={{
                  onChange: props.onChange,
                  onMove: props.onMove,
                  onRemove: props.onRemove,
                }}
              />
            ))}
          </ol>
        ) : (
          <EmptyState icon="note" title="Your note starts here">
            Hover over a passage or a fact in the draft and press <strong>Add</strong>.
            Citations travel with what you take.
          </EmptyState>
        )}
        <div className="st-note-more">
          <Button
            variant="ghost"
            size="sm"
            icon="edit"
            onClick={() => setFresh(props.onAddOwn())}
          >
            Write your own
          </Button>
          {comp.blocks.length ? (
            <Button variant="ghost" size="sm" icon="trash" onClick={props.onClear}>
              Start over
            </Button>
          ) : null}
        </div>
      </div>
      <footer className="st-save-bar">
        {props.saveError ? (
          <div className="st-save-error" role="alert">
            <p>{props.saveError.message}</p>
            {props.saveError.conflict ? (
              <Button size="sm" variant="secondary" onClick={props.onReload}>
                Load the latest version
              </Button>
            ) : null}
          </div>
        ) : (
          <p className="st-muted st-small">
            {why ??
              (comp.target.kind === "existing"
                ? "Saving updates the note and accepts the sources it cites."
                : "Saving creates the note and accepts the sources it cites.")}
          </p>
        )}
        <Button
          variant="primary"
          icon="check"
          busy={props.saving}
          disabled={!!why}
          onClick={props.onSave}
        >
          {comp.target.kind === "existing" ? "Update note" : "Save note"}
        </Button>
      </footer>
    </section>
  );
}
