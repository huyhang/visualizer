// An Akasha article beside the page: its facts and its text, read-only, with
// the way to Akasha's own editor for anything more.

import type { EntityRef } from "../../api/types";
import { ChronosApiError } from "../../api/errors";
import { useDeps } from "../../deps";
import { useEntity } from "../../hooks/queries";
import { plainBody } from "../../logic/text";
import { entityTitle } from "../common/EntityName";
import { Icon } from "../../../components/ui/Icon";
import { Skeleton } from "../../../components/ui/Skeleton";

/** Where Akasha shows this article: its own hash route, wherever it is mounted. */
export function akashaArticleUrl(akashaUrl: string, ref: EntityRef): string {
  const enc = encodeURIComponent;
  return `${akashaUrl}#/${enc(ref.database)}/${enc(ref.collection)}/${enc(ref.id)}`;
}

function factText(value: unknown): string {
  return Array.isArray(value) ? value.map(String).join(", ") : String(value);
}

export function ArticlePane({ book, entity }: { book: string; entity: EntityRef }) {
  const { akashaUrl } = useDeps();
  const { data, error, isPending } = useEntity(book, entity);
  if (isPending) return <Skeleton lines={5} />;
  if (error) {
    const forbidden = error instanceof ChronosApiError && error.isForbidden;
    return (
      <p className="cw-muted">
        {forbidden
          ? "You do not have permission to read this article."
          : "This reference no longer exists in Akasha."}
      </p>
    );
  }
  const doc = data.document;
  const facts = Object.entries(doc).filter(([k]) => k !== "title" && k !== "body");
  const paragraphs = plainBody(typeof doc.body === "string" ? doc.body : "")
    .split(/\n{2,}/)
    .filter((p) => p.trim());
  return (
    <div className="cw-pane">
      <div className="cw-pane-kicker">
        {entity.collection} · {entity.database}
      </div>
      <h2 className="cw-pane-title">{entityTitle(doc, entity.id)}</h2>
      {facts.length ? (
        <dl className="cw-facts">
          {facts.map(([k, v]) => (
            <div key={k} className="cw-fact">
              <dt>{k.replace(/_/g, " ")}</dt>
              <dd>{factText(v)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {paragraphs.length ? (
        <div className="cw-prose">
          {paragraphs.map((p, n) => (
            <p key={n}>{p}</p>
          ))}
        </div>
      ) : facts.length ? null : (
        <p className="cw-muted">This article has no content yet.</p>
      )}
      <a
        className="cw-pane-link"
        href={akashaArticleUrl(akashaUrl, entity)}
        target="_blank"
        rel="noopener"
      >
        Open in Akasha <Icon name="external" size={13} />
      </a>
    </div>
  );
}
