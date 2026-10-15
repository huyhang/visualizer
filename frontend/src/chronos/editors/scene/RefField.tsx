// A field that chooses one or more Akasha articles: the chosen ones as chips,
// and a search of the real canon to add from. Chronos never invents an
// article, so nothing here is typed free-hand.

import { useCallback, useState } from "react";
import type { EntityCandidate, EntityRef } from "../../api/types";
import { useApi } from "../../deps";
import {
  bareRef,
  collectionOptions,
  pick,
  unpick,
  type RefRole,
} from "../../logic/scenes/refs";
import { collectionIcon } from "../../components/common/Chips";
import { EntityName } from "../../components/common/EntityName";
import { TypeAhead, type Option } from "../../components/form/TypeAhead";
import { Icon } from "../../../components/ui/Icon";

export function RefField({
  book,
  role,
  label,
  hint,
  multiple,
  value,
  onChange,
  observed,
  nowhereToSearch,
}: {
  book: string;
  role: RefRole;
  label: string;
  hint?: string;
  multiple: boolean;
  value: EntityRef[];
  onChange: (refs: EntityRef[]) => void;
  /** The collections this book's world has, as the server reported them. */
  observed: string[];
  /** The book names no world and has nothing to infer one from: say so rather than "nothing matches". */
  nowhereToSearch: boolean;
}) {
  const api = useApi();
  const collections = collectionOptions(observed, role);
  const [collection, setCollection] = useState(collections[0] ?? role);
  // Stable, or the type-ahead would search again on every render.
  const search = useCallback(
    async (q: string): Promise<Option<EntityCandidate>[]> => {
      const found = await api.searchEntities(book, { q, collection });
      return found.results.map((r) => ({
        key: `${r.collection}/${r.id}`,
        value: r,
        label: r.title,
        hint: `${r.collection} / ${r.id}`,
      }));
    },
    [api, book, collection],
  );
  return (
    <div className="cw-field">
      <span className="cw-field-label">{label}</span>
      <div className="cw-ref-chips">
        {value.length ? (
          value.map((ref) => (
            <span key={`${ref.collection}/${ref.id}`} className="cw-ref-chip">
              <Icon name={collectionIcon(ref.collection)} size={12} />
              <EntityName book={book} entity={ref} />
              <button
                type="button"
                className="cw-ref-remove"
                aria-label={`Remove ${ref.id}`}
                onClick={() => onChange(unpick(value, ref))}
              >
                <Icon name="x" size={12} />
              </button>
            </span>
          ))
        ) : (
          <span className="cw-muted cw-small">None chosen.</span>
        )}
      </div>
      <div className="cw-ref-search">
        {collections.length > 1 ? (
          <select
            className="st-input st-input-sm cw-ref-collection"
            aria-label={`Which collection to search for ${label.toLowerCase()}`}
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
          >
            {collections.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ) : null}
        <TypeAhead
          search={search}
          label={`Search for ${label.toLowerCase()}`}
          placeholder="Search the canon…"
          emptyText="No article matches — create it in Articles first."
          onPick={(found) => onChange(pick(value, bareRef(found), multiple))}
        />
      </div>
      {nowhereToSearch ? (
        <span className="cw-field-hint">
          This book has no world set, so there is nothing to search. Choose one in the
          book's settings.
        </span>
      ) : hint ? (
        <span className="cw-field-hint">{hint}</span>
      ) : null}
    </div>
  );
}
