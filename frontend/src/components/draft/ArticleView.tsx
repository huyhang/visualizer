import { useMemo } from "react";
import { groupLines, parseLines } from "../../logic/wikitext";
import type { DraftActions } from "./actions";
import { Passage } from "./Passage";

/** The draft as an article: every paragraph and list item a passage to pick up. */
export function ArticleView({
  body,
  draft,
  actions,
}: {
  body: string;
  draft: string;
  actions: DraftActions;
}) {
  const groups = useMemo(() => groupLines(parseLines(body)), [body]);
  if (!groups.length) return <p className="st-muted">This draft has no text.</p>;
  return (
    <div className="st-article">
      {groups.map((group) =>
        group.kind === "list" ? (
          <ul key={group.items[0]!.index}>
            {group.items.map(({ line, index }) => (
              <Passage key={index} as="li" line={line} draft={draft} actions={actions} />
            ))}
          </ul>
        ) : (
          <Passage key={group.index} line={group.line} draft={draft} actions={actions} />
        ),
      )}
    </div>
  );
}
