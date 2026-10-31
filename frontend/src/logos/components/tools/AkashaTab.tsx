// What canon the selected words might name, the articles linked to this
// section, and what a phrase linked in the prose points at.

import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { messageOf } from "../../api/errors";
import type { Entity, LinkedArticle } from "../../api/types";
import type { ArticleRef } from "../../doc/types";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Spinner } from "../../../components/ui/Spinner";
import type { AkashaSubject } from "../../hooks/useAkasha";
import { isLinked, sameArticle } from "../../logic/linked";

type Previewed = Pick<Entity, "database_title" | "collection_title" | "fields"> & {
  title: string;
};

/** An article at a glance: its name, where it lives, its facts. */
function ArticleCard({ article, children }: { article: Previewed; children: ReactNode }) {
  return (
    <article className="lw-card lw-entity">
      <header>
        <strong>{article.title}</strong>
        <small>
          {article.database_title} / {article.collection_title}
        </small>
      </header>
      {article.fields?.length ? (
        <dl className="lw-entity-fields">
          {article.fields.map((field) => [
            <dt key={`${field.name}-t`}>{field.name}</dt>,
            <dd key={`${field.name}-d`}>{field.value}</dd>,
          ])}
        </dl>
      ) : null}
      <div className="lw-card-actions">{children}</div>
    </article>
  );
}

function EntityCard({
  entity,
  where,
  linked,
  busy,
  onLink,
  onOpen,
}: {
  entity: Entity;
  where: string;
  linked: boolean;
  busy: boolean;
  onLink: (entity: Entity) => void;
  onOpen: (ref: ArticleRef) => void;
}) {
  return (
    <ArticleCard article={entity}>
      {linked ? (
        <span className="lw-linked-badge">
          <Icon name="check" size={14} /> Linked to this {where}
        </span>
      ) : (
        <Button
          size="sm"
          variant="primary"
          icon="link"
          disabled={busy}
          title={`List this article beside this ${where}, without marking any words`}
          onClick={() => onLink(entity)}
        >
          Link to {where}
        </Button>
      )}
      <Button size="sm" variant="ghost" icon="external" onClick={() => onOpen(entity)}>
        Open article
      </Button>
    </ArticleCard>
  );
}

function LinkedList({
  linked,
  where,
  busy,
  previewing,
  onPreview,
  onOpen,
  onUnlink,
}: {
  linked: UseQueryResult<LinkedArticle[]>;
  where: string;
  busy: boolean;
  /** The article the tab is previewing, if one of these. */
  previewing: ArticleRef | null;
  onPreview: (ref: LinkedArticle) => void;
  onOpen: (ref: ArticleRef) => void;
  onUnlink: (ref: LinkedArticle) => void;
}) {
  const rows = linked.data ?? [];
  return (
    <section className="lw-linked" aria-label={`Linked to this ${where}`}>
      <h3 className="lw-kicker">Linked to this {where}</h3>
      {linked.isLoading ? (
        <p className="lw-muted lw-inline">
          <Spinner size={14} /> Loading…
        </p>
      ) : linked.error ? (
        <p className="st-error-text">
          {messageOf(linked.error, "The linked articles could not be loaded.")}
        </p>
      ) : rows.length ? (
        <ul className="lw-linked-list">
          {rows.map((row) => {
            const name = row.title ?? (row.missing ? row.id : "An article you can't open");
            const shown = previewing !== null && sameArticle(previewing, row);
            const label = (
              <>
                <strong>{name}</strong>
                <small>{row.missing ? "No longer in Akasha" : row.collection_title}</small>
              </>
            );
            return (
              <li
                key={`${row.database}/${row.collection}/${row.id}`}
                className={`lw-linked-row${row.title === null ? " is-unseen" : ""}${shown ? " is-shown" : ""}`}
              >
                {row.title === null ? (
                  <span className="lw-linked-name">{label}</span>
                ) : (
                  <button
                    type="button"
                    className="lw-linked-name"
                    aria-current={shown || undefined}
                    title={`Preview ${name}`}
                    onClick={() => onPreview(row)}
                  >
                    {label}
                  </button>
                )}
                {row.missing || row.title === null ? null : (
                  <button
                    type="button"
                    className="st-icon-btn"
                    aria-label={`Open ${name} in Akasha`}
                    title="Open article"
                    onClick={() => onOpen(row)}
                  >
                    <Icon name="external" size={15} />
                  </button>
                )}
                <button
                  type="button"
                  className="st-icon-btn"
                  aria-label={`Unlink ${name}`}
                  title={`Unlink from this ${where}`}
                  disabled={busy}
                  onClick={() => onUnlink(row)}
                >
                  <Icon name="x" size={15} />
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="lw-muted lw-small">
          Nothing yet. Look a name up and link it, and its article stays listed here — and
          goes to the Editor as reference.
        </p>
      )}
    </section>
  );
}

export function AkashaTab({
  subject,
  results,
  linked,
  where,
  busy,
  onLink,
  onPreview,
  onUnlinkArticle,
  onOpen,
  onUnlink,
}: {
  subject: AkashaSubject;
  results: UseQueryResult<Entity[]>;
  /** The articles linked to this section. */
  linked: UseQueryResult<LinkedArticle[]>;
  /** What the section is, to name it: "chapter", "prologue". */
  where: string;
  /** A change to the linked articles is being saved. */
  busy: boolean;
  onLink: (entity: Entity) => void;
  /** Show a linked article in the tab. */
  onPreview: (ref: LinkedArticle) => void;
  onUnlinkArticle: (ref: LinkedArticle) => void;
  onOpen: (ref: ArticleRef) => void;
  /** Take the link off the phrase in the prose. */
  onUnlink: () => void;
}) {
  const rows = linked.data ?? [];
  // A linked article stays previewed only while it is linked and readable.
  const previewed =
    subject.kind === "linked"
      ? rows.find((row) => sameArticle(row, subject.ref) && row.title !== null)
      : undefined;
  const list = (
    <LinkedList
      linked={linked}
      where={where}
      busy={busy}
      previewing={previewed ?? null}
      onPreview={onPreview}
      onOpen={onOpen}
      onUnlink={onUnlinkArticle}
    />
  );
  if (previewed) {
    return (
      <div className="lw-stack">
        <ArticleCard article={{ ...previewed, title: previewed.title ?? previewed.id }}>
          <Button
            size="sm"
            variant="ghost"
            icon="external"
            onClick={() => onOpen(previewed)}
          >
            Open article
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon="x"
            disabled={busy}
            onClick={() => onUnlinkArticle(previewed)}
          >
            Unlink from {where}
          </Button>
        </ArticleCard>
        {list}
      </div>
    );
  }
  if (subject.kind === "idle" || subject.kind === "linked") {
    return (
      <div className="lw-stack">
        <div className="lw-empty">
          <span className="lw-empty-icon">
            <Icon name="book" size={20} />
          </span>
          <p>
            Select a name in the manuscript and right-click it — or press <kbd>⌘K</kbd> — to
            look it up in Akasha.
          </p>
        </div>
        {list}
      </div>
    );
  }
  if (subject.kind === "mention") {
    const { mention } = subject;
    return (
      <div className="lw-stack">
        <p className="lw-kicker">Linked: “{mention.text}”</p>
        <article className="lw-card lw-entity">
          <header>
            <strong>{mention.text}</strong>
            <small>
              {mention.database} / {mention.collection} / {mention.id}
            </small>
          </header>
          <div className="lw-card-actions">
            <Button
              size="sm"
              variant="ghost"
              icon="external"
              onClick={() => onOpen(mention)}
            >
              Open article
            </Button>
            <Button
              size="sm"
              variant="ghost"
              title="Keep the words, remove the Akasha reference"
              onClick={onUnlink}
            >
              Unlink
            </Button>
          </div>
        </article>
        {list}
      </div>
    );
  }
  return (
    <div className="lw-stack">
      <p className="lw-kicker">Selected: “{subject.text}”</p>
      {results.isLoading ? (
        <p className="lw-muted lw-inline">
          <Spinner size={14} /> Searching Akasha…
        </p>
      ) : results.error ? (
        <p className="st-error-text">{messageOf(results.error, "Akasha lookup failed.")}</p>
      ) : results.data?.length ? (
        results.data.map((entity) => (
          <EntityCard
            key={`${entity.database}/${entity.collection}/${entity.id}`}
            entity={entity}
            where={where}
            linked={isLinked(rows, entity)}
            busy={busy || linked.isLoading}
            onLink={onLink}
            onOpen={onOpen}
          />
        ))
      ) : (
        <p className="lw-muted">No readable Akasha entity matched.</p>
      )}
      {list}
    </div>
  );
}
