import { Popover } from "radix-ui";
import { siteOf } from "../../logic/format";
import { Icon } from "../ui/Icon";
import { useCitations } from "./CitationContext";

/** A superscript number that opens the source and the exact words taken from it. */
export function CitationChip({ target }: { target: string }) {
  const info = useCitations();
  const number = info.number(target);
  const source = info.source(target);
  const accepted = target.startsWith("sources/");
  if (!source) {
    return (
      <span className={`st-cite is-plain${accepted ? " is-accepted" : ""}`} title={target}>
        {number ?? "†"}
      </span>
    );
  }
  const quotes = info.quotes(target);
  return (
    <Popover.Root>
      <Popover.Trigger
        className={`st-cite${accepted ? " is-accepted" : ""}`}
        aria-label={`Source ${number}: ${source.title}`}
      >
        {number}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="st-popover st-cite-card"
          sideOffset={6}
          collisionPadding={12}
        >
          <p className="st-cite-site">
            {siteOf(source.url)}
            {accepted ? (
              <span className="st-cite-flag">already in your sources</span>
            ) : null}
          </p>
          <p className="st-cite-title">{source.title}</p>
          {quotes.length ? (
            <ul className="st-quotes">
              {quotes.slice(0, 3).map((quote) => (
                <li key={quote}>
                  <blockquote>“{quote}”</blockquote>
                </li>
              ))}
            </ul>
          ) : (
            <p className="st-muted st-small">
              No quote from this page made it into a fact.
            </p>
          )}
          <div className="st-cite-actions">
            <a
              className="st-btn st-btn-ghost st-btn-sm"
              href={source.url}
              target="_blank"
              rel="noreferrer noopener"
            >
              <Icon name="external" size={14} /> Open page
            </a>
            {info.onDistrust && !accepted ? (
              <button
                type="button"
                className="st-btn st-btn-ghost st-btn-sm"
                onClick={() => info.onDistrust?.(target)}
              >
                <Icon name="ban" size={14} /> Distrust
              </button>
            ) : null}
          </div>
          <Popover.Arrow className="st-popover-arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
