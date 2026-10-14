import { useState } from "react";
import type { ImageBlock, NoteBlock, TextBlock } from "../../logic/compose";
import type { ImageAlign } from "../../logic/wikitext";
import type { DraftActions } from "../draft/actions";
import { IconButton } from "../ui/Button";
import { AutoTextarea } from "../ui/AutoTextarea";
import { WikiPreview } from "./WikiPreview";

export interface BlockHandlers {
  onChange(id: string, patch: Partial<TextBlock> | Partial<ImageBlock>): void;
  onMove(id: string, delta: number): void;
  onRemove(id: string): void;
}

/** One block of the note: read as it will look, click to edit, move or remove. */
export function NoteBlockView({
  block,
  first,
  last,
  startEditing,
  linkTo,
  handlers,
}: {
  block: NoteBlock;
  first: boolean;
  last: boolean;
  startEditing: boolean;
  linkTo: DraftActions["linkTo"];
  handlers: BlockHandlers;
}) {
  const existing = block.kind === "text" && !!block.existing;
  const origin =
    block.kind === "image"
      ? "Image"
      : existing
        ? "The note so far"
        : block.draft
          ? "From the draft"
          : "Your words";
  return (
    <li className={`st-block is-${block.kind}${existing ? " is-existing" : ""}`}>
      <div className="st-block-head">
        <span className="st-block-origin">{origin}</span>
        <span className="st-block-tools">
          <IconButton
            icon="arrowUp"
            label="Move up"
            disabled={first}
            onClick={() => handlers.onMove(block.id, -1)}
          />
          <IconButton
            icon="arrowDown"
            label="Move down"
            disabled={last}
            onClick={() => handlers.onMove(block.id, 1)}
          />
          <IconButton
            icon="x"
            label="Remove from note"
            onClick={() => handlers.onRemove(block.id)}
          />
        </span>
      </div>
      {block.kind === "text" ? (
        <TextBlockBody
          block={block}
          startEditing={startEditing}
          linkTo={linkTo}
          onChange={handlers.onChange}
        />
      ) : (
        <ImageBlockBody block={block} onChange={handlers.onChange} />
      )}
    </li>
  );
}

function TextBlockBody({
  block,
  startEditing,
  linkTo,
  onChange,
}: {
  block: TextBlock;
  startEditing: boolean;
  linkTo: DraftActions["linkTo"];
  onChange: BlockHandlers["onChange"];
}) {
  const [editing, setEditing] = useState(startEditing);
  if (editing) {
    return (
      <AutoTextarea
        className="st-block-editor"
        value={block.text}
        autoFocus
        maxRows={24}
        onChange={(e) => onChange(block.id, { text: e.target.value })}
        onBlur={() => setEditing(false)}
        aria-label="Edit this block (wikitext)"
      />
    );
  }
  return (
    <div
      className="st-block-preview"
      role="button"
      tabIndex={0}
      title="Click to edit"
      onClick={(e) => {
        if (!(e.target as HTMLElement).closest("a, button")) setEditing(true);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" && e.target === e.currentTarget) setEditing(true);
      }}
    >
      <WikiPreview text={block.text} linkTo={linkTo} />
    </div>
  );
}

const ALIGNS: { value: ImageAlign; label: string }[] = [
  { value: "left", label: "Left" },
  { value: "center", label: "Centre" },
  { value: "right", label: "Right" },
  { value: "full", label: "Full width" },
];

function ImageBlockBody({
  block,
  onChange,
}: {
  block: ImageBlock;
  onChange: BlockHandlers["onChange"];
}) {
  return (
    <div className="st-block-image">
      <img src={block.previewUrl} alt={block.caption} />
      <div className="st-block-image-fields">
        <input
          className="st-input st-input-sm"
          value={block.caption}
          onChange={(e) => onChange(block.id, { caption: e.target.value })}
          aria-label="Caption"
          placeholder="Caption"
        />
        <select
          className="st-input st-input-sm"
          value={block.align}
          onChange={(e) => onChange(block.id, { align: e.target.value as ImageAlign })}
          aria-label="Placement"
        >
          {ALIGNS.map((a) => (
            <option key={a.value} value={a.value}>
              {a.label}
            </option>
          ))}
        </select>
        <small className="st-muted">
          {block.mediaId ? "In your library" : "Imported when you save"}
        </small>
      </div>
    </div>
  );
}
