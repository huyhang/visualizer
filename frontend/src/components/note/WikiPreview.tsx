import { useMemo } from "react";
import { groupLines, parseLines, type Line } from "../../logic/wikitext";
import type { DraftActions } from "../draft/actions";
import { InlineContent } from "../draft/InlineContent";
import { Icon } from "../ui/Icon";

/** Wikitext as it will read in the article -- without the passage tools. */
export function WikiPreview({
  text,
  linkTo,
}: {
  text: string;
  linkTo: DraftActions["linkTo"];
}) {
  const groups = useMemo(() => groupLines(parseLines(text)), [text]);
  if (!groups.length) return <p className="st-muted st-small">Empty — click to write.</p>;
  return (
    <div className="st-wiki">
      {groups.map((group) =>
        group.kind === "list" ? (
          <ul key={group.items[0]!.index}>
            {group.items.map(({ line, index }) => (
              <li key={index}>{renderInlines(line, linkTo)}</li>
            ))}
          </ul>
        ) : (
          <LineView key={group.index} line={group.line} linkTo={linkTo} />
        ),
      )}
    </div>
  );
}

function LineView({ line, linkTo }: { line: Line; linkTo: DraftActions["linkTo"] }) {
  if (line.kind === "image") {
    return (
      <p className="st-wiki-image">
        <Icon name="image" size={14} /> {line.caption || "Image"}
      </p>
    );
  }
  if (line.kind === "heading") {
    const H = `h${Math.min(line.level + 1, 6)}` as "h3";
    return <H>{renderInlines(line, linkTo)}</H>;
  }
  return <p>{renderInlines(line, linkTo)}</p>;
}

function renderInlines(line: Line, linkTo: DraftActions["linkTo"]) {
  return line.kind === "image" ? null : (
    <InlineContent inlines={line.inlines} linkTo={linkTo} />
  );
}
