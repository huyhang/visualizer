// The book's ending: the one scene every thread must reach. Chosen here from
// the book's own scenes; saving the book sends it with everything else.

import { useCallback } from "react";
import { useApi } from "../../deps";
import { useEvent } from "../../hooks/queries";
import type { Option } from "../../components/form/TypeAhead";
import { TypeAhead } from "../../components/form/TypeAhead";
import { Field } from "../../components/form/Fields";
import { Chip } from "../../components/common/Chips";
import { Button } from "../../../components/ui/Button";

export function TerminusField({
  book,
  value,
  onChange,
}: {
  book: string;
  value: string | null;
  onChange: (scene: string | null) => void;
}) {
  const api = useApi();
  const { data: scene } = useEvent(book, value, null);
  const search = useCallback(
    async (query: string): Promise<Option<string>[]> => {
      const page = await api.listEvents(book, { filter: query, perPage: 20 });
      return page.events.map((e) => ({
        key: e.id,
        value: e.id,
        label: e.title || e.id,
        hint: e.when,
      }));
    },
    [api, book],
  );
  return (
    <Field
      label="The ending"
      hint="The scene every thread must reach. A thread that stops short is reported, never refused."
    >
      <div className="cw-terminus">
        {value ? (
          <span className="cw-terminus-current">
            <Chip tone="accent" icon="flag">
              {scene?.title || value}
            </Chip>
            <Button size="sm" variant="ghost" onClick={() => onChange(null)}>
              Clear
            </Button>
          </span>
        ) : (
          <span className="cw-muted cw-small">No ending designated yet.</span>
        )}
        <TypeAhead
          label="Choose the ending"
          placeholder={value ? "Choose another scene…" : "Search the book's scenes…"}
          search={search}
          onPick={(id) => onChange(id)}
        />
      </div>
    </Field>
  );
}
