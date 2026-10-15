// What a review reads and checks for: the three checks, the dialect, whether a
// second machine re-judges each issue, any extra Akasha articles to send -- and
// a look at exactly what the editor will read, and what it will be left without.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { SectionAddress } from "../../api/LogosApi";
import { messageOf } from "../../api/errors";
import type { Check, Dialect, Entity, VerifyMode } from "../../api/types";
import { Icon } from "../../../components/ui/Icon";
import { Spinner } from "../../../components/ui/Spinner";
import { useDeps } from "../../deps";
import { CHECK_HINTS, CHECK_LABELS, CHECKS } from "../../logic/review";

export interface Included {
  ref: string;
  title: string;
}

export interface AskSettings {
  checks: Check[];
  verify: VerifyMode;
  dialect: Dialect;
  include: Included[];
}

const MAX_INCLUDED = 20;

const SKIP_REASONS: Record<string, string> = {
  unavailable: "Missing, or not yours to read",
  unverified: "Research not yet verified",
  unreviewed_research: "Still in the research inbox",
  source: "A source, not a reference",
  over_limit: "Over the 40-article limit",
};

const KIND_LABELS: Record<string, string> = {
  deviation: "Deviation",
  watchlist: "Watchlist",
  canon: "Canon",
  research: "Research",
};

const refOf = (entity: Entity) => `${entity.database}/${entity.collection}/${entity.id}`;

function IncludePicker({
  book,
  include,
  onChange,
}: {
  book: string;
  include: Included[];
  onChange: (include: Included[]) => void;
}) {
  const { api } = useDeps();
  const [query, setQuery] = useState("");
  const wanted = query.trim();
  const found = useQuery({
    queryKey: ["entities", book, wanted],
    queryFn: () => api.entities(book, wanted),
    enabled: wanted.length >= 2,
    staleTime: 30_000,
  });
  const chosen = new Set(include.map((item) => item.ref));
  const full = include.length >= MAX_INCLUDED;
  return (
    <fieldset className="st-field lw-include">
      <legend>More articles to send</legend>
      {include.length ? (
        <ul className="lw-chips">
          {include.map((item) => (
            <li key={item.ref} className="lw-chip">
              {item.title}
              <button
                type="button"
                aria-label={`Stop sending ${item.title}`}
                onClick={() => onChange(include.filter((i) => i.ref !== item.ref))}
              >
                <Icon name="x" size={12} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <input
        className="st-input st-input-sm"
        type="search"
        placeholder={full ? `At most ${MAX_INCLUDED} articles` : "Search Akasha…"}
        aria-label="Search Akasha for an article to send"
        disabled={full}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {wanted.length >= 2 && !full ? (
        <ul className="lw-include-results">
          {found.isLoading ? (
            <li className="lw-muted lw-small">Searching…</li>
          ) : (
            (found.data ?? [])
              .filter((e) => !chosen.has(refOf(e)))
              .slice(0, 6)
              .map((entity) => (
                <li key={refOf(entity)}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange([...include, { ref: refOf(entity), title: entity.title }]);
                      setQuery("");
                    }}
                  >
                    <strong>{entity.title}</strong>
                    <small>{entity.collection_title}</small>
                  </button>
                </li>
              ))
          )}
        </ul>
      ) : null}
    </fieldset>
  );
}

function WhatItReads({
  at,
  draft,
  include,
  settled,
}: {
  at: SectionAddress;
  draft: string;
  include: Included[];
  settled: () => Promise<boolean>;
}) {
  const { api } = useDeps();
  const refs = include.map((item) => item.ref);
  const preview = useQuery({
    queryKey: ["llm-review-references", at.book, at.volume, at.section, draft, refs],
    queryFn: async () => {
      // The server reads the saved draft: words that could not be saved are not in it.
      const saved = await settled();
      return { ...(await api.reviewReferences(at, draft, refs)), saved };
    },
  });
  if (preview.isLoading) {
    return (
      <p className="lw-muted lw-small lw-inline">
        <Spinner size={12} /> Gathering what the chapter mentions…
      </p>
    );
  }
  if (preview.error) return <p className="st-error-text">{messageOf(preview.error)}</p>;
  const data = preview.data!;
  return (
    <div className="lw-reads">
      {data.saved ? null : (
        <p className="lw-small lw-muted">
          Your latest words are not saved yet, so this is what the saved draft mentions.
        </p>
      )}
      <p className="lw-small">
        The chapter, and {data.references.length}{" "}
        {data.references.length === 1 ? "article" : "articles"}:
      </p>
      <ul className="lw-reads-list">
        {data.references.map((reference) => (
          <li key={reference.ref}>
            <span className={`lw-ref-kind lw-ref-${reference.kind}`}>
              {KIND_LABELS[reference.kind] ?? reference.kind}
            </span>
            {reference.title}
          </li>
        ))}
      </ul>
      {data.skipped.length ? (
        <>
          <p className="lw-small lw-muted">Left out:</p>
          <ul className="lw-reads-list is-skipped">
            {data.skipped.map((skipped) => (
              <li key={skipped.ref}>
                <span className="lw-ref-path">
                  {skipped.ref.split("/").slice(1).join(" / ")}
                </span>
                <small>{SKIP_REASONS[skipped.reason] ?? skipped.reason}</small>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

export function AskOptions({
  at,
  draft,
  settings,
  onChange,
  settled,
}: {
  at: SectionAddress;
  draft: string;
  settings: AskSettings;
  onChange: (settings: AskSettings) => void;
  settled: () => Promise<boolean>;
}) {
  const [reading, setReading] = useState(false);
  const toggleCheck = (check: Check) => {
    const has = settings.checks.includes(check);
    const checks = has
      ? settings.checks.filter((c) => c !== check)
      : CHECKS.filter((c) => c === check || settings.checks.includes(c));
    if (checks.length) onChange({ ...settings, checks });
  };
  return (
    <div className="lw-ask-options">
      <fieldset className="st-field">
        <legend>Check for</legend>
        {CHECKS.map((check) => (
          <label key={check} className="st-check">
            <input
              type="checkbox"
              checked={settings.checks.includes(check)}
              disabled={settings.checks.length === 1 && settings.checks.includes(check)}
              onChange={() => toggleCheck(check)}
            />
            <span>
              {CHECK_LABELS[check]}
              <small>{CHECK_HINTS[check]}</small>
            </span>
          </label>
        ))}
      </fieldset>
      <div className="lw-option-row">
        <label className="st-field">
          <span>English</span>
          <select
            className="st-input st-input-sm"
            value={settings.dialect}
            onChange={(event) =>
              onChange({ ...settings, dialect: event.target.value as Dialect })
            }
          >
            <option value="en-US">US</option>
            <option value="en-GB">UK</option>
          </select>
        </label>
        <label className="st-field">
          <span>Second check</span>
          <select
            className="st-input st-input-sm"
            value={settings.verify}
            onChange={(event) =>
              onChange({ ...settings, verify: event.target.value as VerifyMode })
            }
          >
            <option value="auto">When available</option>
            <option value="required">Required</option>
            <option value="off">Off</option>
          </select>
        </label>
      </div>
      <IncludePicker
        book={at.book}
        include={settings.include}
        onChange={(include) => onChange({ ...settings, include })}
      />
      <button
        type="button"
        className="lw-disclosure"
        aria-expanded={reading}
        onClick={() => setReading((open) => !open)}
      >
        <Icon name={reading ? "chevronDown" : "chevronRight"} size={14} />
        What the editor will read
      </button>
      {reading ? (
        <WhatItReads at={at} draft={draft} include={settings.include} settled={settled} />
      ) : null}
    </div>
  );
}
