import { Fragment } from "react";
import type { ArticleRef } from "../../api/types";
import { isCitation } from "../../logic/citations";
import type { Inline } from "../../logic/wikitext";
import { CitationChip } from "./CitationChip";

/** Rendered wikitext inline content: formatting, citations, and links into Akasha. */
export function InlineContent({
  inlines,
  linkTo,
}: {
  inlines: Inline[];
  linkTo: (target: string) => { href: string; ref: ArticleRef } | null;
}) {
  return (
    <>
      {inlines.map((inline, n) => {
        switch (inline.kind) {
          case "text":
            return <Fragment key={n}>{inline.text}</Fragment>;
          case "bold":
            return (
              <strong key={n}>
                <InlineContent inlines={inline.children} linkTo={linkTo} />
              </strong>
            );
          case "italic":
            return (
              <em key={n}>
                <InlineContent inlines={inline.children} linkTo={linkTo} />
              </em>
            );
          case "link": {
            if (isCitation(inline.target))
              return <CitationChip key={n} target={inline.target} />;
            const resolved = linkTo(inline.target);
            const label = inline.label ?? resolved?.ref.id ?? inline.target;
            return resolved ? (
              <a
                key={n}
                className="st-wikilink"
                href={resolved.href}
                target="_blank"
                rel="noreferrer"
              >
                {label}
              </a>
            ) : (
              <span key={n} className="st-wikilink is-dead">
                {label}
              </span>
            );
          }
        }
      })}
    </>
  );
}
