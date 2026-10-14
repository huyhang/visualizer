import type { Fact, SourceRow } from "../../api/types";
import { quotesFrom } from "../../logic/citations";
import { plural, siteOf } from "../../logic/format";
import { Badge } from "../ui/Badge";
import { Icon } from "../ui/Icon";
import type { DraftActions } from "./actions";

/** Every page the draft read, what it took from each, and a way to distrust one. */
export function SourcesView({
  sources,
  facts,
  actions,
}: {
  sources: SourceRow[];
  facts: Fact[];
  actions: DraftActions;
}) {
  return (
    <ol className="st-sources">
      {sources.map((source, n) => {
        const quotes = quotesFrom(source.ref, facts);
        const accepted = source.ref.startsWith("sources/");
        return (
          <li key={source.ref} className="st-source">
            <span className="st-source-number">{n + 1}</span>
            <div className="st-source-body">
              <a
                className="st-source-title"
                href={source.url}
                target="_blank"
                rel="noreferrer noopener"
              >
                {source.title} <Icon name="external" size={12} />
              </a>
              <p className="st-source-site">
                {siteOf(source.url)} · {plural(quotes.length, "quote")}
                {accepted ? (
                  <Badge tone="accent" title="Already accepted into this world's sources">
                    In your sources
                  </Badge>
                ) : null}
              </p>
              {quotes[0] ? (
                <blockquote className="st-source-quote">“{quotes[0]}”</blockquote>
              ) : null}
            </div>
            {!accepted ? (
              <button
                type="button"
                className="st-tool"
                onClick={() => actions.steer([source.ref])}
                title="Research again without this source"
              >
                <Icon name="ban" size={14} />
                <span>Distrust</span>
              </button>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
