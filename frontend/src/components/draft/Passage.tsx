import { citedByLine, isCitation, isInboxRef } from "../../logic/citations";
import { plainText, type Line } from "../../logic/wikitext";
import { Icon } from "../ui/Icon";
import type { DraftActions } from "./actions";
import { InlineContent } from "./InlineContent";

/**
 * One line of a draft, with what can be done with it on hover (or focus, or a
 * tap on a touch screen): add it to the note, dig deeper, distrust its sources.
 */
export function Passage({
  line,
  draft,
  actions,
  as: Tag = "p",
}: {
  line: Line;
  draft: string;
  actions: DraftActions;
  as?: "p" | "li";
}) {
  if (line.kind === "image") return null;
  if (line.kind === "heading") {
    const H = `h${Math.min(line.level + 1, 6)}` as "h3";
    return (
      <H className="st-draft-heading">
        <InlineContent inlines={line.inlines} linkTo={actions.linkTo} />
      </H>
    );
  }
  const text = plainText(line.inlines, isCitation);
  const distrustable = citedByLine(line).filter(isInboxRef);
  const added = actions.hasText(line.source);

  return (
    <Tag className={`st-passage${added ? " is-added" : ""}`} tabIndex={0}>
      <span className="st-passage-text">
        <InlineContent inlines={line.inlines} linkTo={actions.linkTo} />
      </span>
      <span className="st-passage-tools" role="toolbar" aria-label="Passage actions">
        <button
          type="button"
          className="st-tool is-primary"
          onClick={() => actions.addText(line.source, draft)}
          disabled={added}
          title={added ? "Already in your note" : "Add to note"}
        >
          <Icon name={added ? "check" : "plus"} size={14} />
          <span>{added ? "In note" : "Add"}</span>
        </button>
        {text ? (
          <button
            type="button"
            className="st-tool"
            onClick={() => actions.digDeeper(text)}
            title="Research this further"
          >
            <Icon name="deeper" size={14} />
            <span>Dig deeper</span>
          </button>
        ) : null}
        {distrustable.length ? (
          <button
            type="button"
            className="st-tool"
            onClick={() => actions.steer(distrustable)}
            title="Research the draft again without these sources"
          >
            <Icon name="ban" size={14} />
            <span>Distrust</span>
          </button>
        ) : null}
      </span>
    </Tag>
  );
}
