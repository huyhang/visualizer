import { useState } from "react";
import type { DroppedFact, Fact, FactCheck } from "../../api/types";
import { factAsWikitext } from "../../logic/citations";
import { plural } from "../../logic/format";
import { parseInline } from "../../logic/wikitext";
import { Badge, type BadgeTone } from "../ui/Badge";
import { Icon } from "../ui/Icon";
import type { DraftActions } from "./actions";
import { InlineContent } from "./InlineContent";

const CHECKS: Record<FactCheck, { tone: BadgeTone; label: string }> = {
  supported: { tone: "ok", label: "Supported" },
  partial: { tone: "warn", label: "Partly supported" },
  unchecked: { tone: "neutral", label: "Not second-checked" },
};

const REASONS: Record<string, string> = {
  quote_not_found: "Its quote is not on the page",
  no_citation: "It cited no source",
  source_unreachable: "Its source could not be read",
  unsupported: "The second check found it unsupported",
};

/** Each fact on its own, with its verdict: the most precise material for a note. */
export function FactsView({
  facts,
  dropped,
  draft,
  actions,
}: {
  facts: Fact[];
  dropped: DroppedFact[];
  draft: string;
  actions: DraftActions;
}) {
  const [showDropped, setShowDropped] = useState(false);
  const notAdded = facts.map(factAsWikitext).filter((text) => !actions.hasText(text));

  return (
    <div className="st-facts">
      {facts.length > 1 && notAdded.length ? (
        <div className="st-facts-bar">
          <span className="st-muted st-small">
            {plural(facts.length, "fact")}, each with its quote checked against the page.
          </span>
          <button
            type="button"
            className="st-btn st-btn-ghost st-btn-sm"
            onClick={() => notAdded.forEach((text) => actions.addText(text, draft))}
          >
            <Icon name="plus" size={14} /> Add all
          </button>
        </div>
      ) : null}
      <ul className="st-fact-list">
        {facts.map((fact) => {
          const text = factAsWikitext(fact);
          const added = actions.hasText(text);
          const check = CHECKS[fact.check];
          return (
            <li key={text} className={`st-fact${added ? " is-added" : ""}`}>
              <div className="st-fact-text">
                <InlineContent
                  inlines={parseInline(text.replace(/^\*\s+/, ""))}
                  linkTo={actions.linkTo}
                />
              </div>
              <div className="st-fact-meta">
                <Badge tone={check.tone}>{check.label}</Badge>
                <button
                  type="button"
                  className="st-tool is-primary"
                  disabled={added}
                  onClick={() => actions.addText(text, draft)}
                >
                  <Icon name={added ? "check" : "plus"} size={14} />
                  <span>{added ? "In note" : "Add"}</span>
                </button>
                <button
                  type="button"
                  className="st-tool"
                  onClick={() => actions.digDeeper(fact.text)}
                >
                  <Icon name="deeper" size={14} />
                  <span>Dig deeper</span>
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      {dropped.length ? (
        <section className="st-dropped">
          <button
            type="button"
            className="st-disclosure"
            aria-expanded={showDropped}
            onClick={() => setShowDropped(!showDropped)}
          >
            <Icon name={showDropped ? "chevronDown" : "chevronRight"} size={14} />
            What didn't make it ({dropped.length})
          </button>
          {showDropped ? (
            <ul>
              {dropped.map((fact) => (
                <li key={`${fact.reason}:${fact.text}`}>
                  <span className="st-dropped-text">{fact.text}</span>
                  <span className="st-dropped-reason">
                    {REASONS[fact.reason] ?? fact.reason}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
