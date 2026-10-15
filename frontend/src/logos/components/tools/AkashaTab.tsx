// What canon the selected words might name, and what a linked phrase points at.

import type { UseQueryResult } from "@tanstack/react-query";
import { messageOf } from "../../api/errors";
import type { Entity } from "../../api/types";
import type { ArticleRef } from "../../doc/types";
import { Button } from "../../../components/ui/Button";
import { Icon } from "../../../components/ui/Icon";
import { Spinner } from "../../../components/ui/Spinner";
import type { AkashaSubject } from "../../hooks/useAkasha";

function EntityCard({
  entity,
  canLink,
  onLink,
  onOpen,
}: {
  entity: Entity;
  canLink: boolean;
  onLink: (entity: Entity) => void;
  onOpen: (ref: ArticleRef) => void;
}) {
  return (
    <article className="lw-card lw-entity">
      <header>
        <strong>{entity.title}</strong>
        <small>
          {entity.database_title} / {entity.collection_title}
        </small>
      </header>
      {entity.fields?.length ? (
        <dl className="lw-entity-fields">
          {entity.fields.map((field) => [
            <dt key={`${field.name}-t`}>{field.name}</dt>,
            <dd key={`${field.name}-d`}>{field.value}</dd>,
          ])}
        </dl>
      ) : null}
      <div className="lw-card-actions">
        <Button
          size="sm"
          variant="primary"
          icon="link"
          disabled={!canLink}
          title={
            canLink
              ? "Keep these words linked to Akasha"
              : "Select words within one paragraph to link"
          }
          onClick={() => onLink(entity)}
        >
          Link mention
        </Button>
        <Button size="sm" variant="ghost" icon="external" onClick={() => onOpen(entity)}>
          Open article
        </Button>
      </div>
    </article>
  );
}

export function AkashaTab({
  subject,
  results,
  onLink,
  onOpen,
  onUnlink,
}: {
  subject: AkashaSubject;
  results: UseQueryResult<Entity[]>;
  onLink: (entity: Entity) => void;
  onOpen: (ref: ArticleRef) => void;
  onUnlink: () => void;
}) {
  if (subject.kind === "idle") {
    return (
      <div className="lw-empty">
        <span className="lw-empty-icon">
          <Icon name="book" size={20} />
        </span>
        <p>
          Select a name in the manuscript and right-click it — or press <kbd>⌘K</kbd> — to
          look it up in Akasha.
        </p>
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
            canLink={subject.linkable}
            onLink={onLink}
            onOpen={onOpen}
          />
        ))
      ) : (
        <p className="lw-muted">No readable Akasha entity matched.</p>
      )}
    </div>
  );
}
