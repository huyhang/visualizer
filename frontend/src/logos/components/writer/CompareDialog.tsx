// Two drafts side by side, paragraph by paragraph, aligned by their stable
// block ids, with how each reads in numbers.

import { useState } from "react";
import type { SectionAddress } from "../../api/LogosApi";
import { messageOf } from "../../api/errors";
import type { DraftRow } from "../../api/types";
import { Button } from "../../../components/ui/Button";
import { Modal } from "../../../components/ui/Modal";
import { useDeps } from "../../deps";
import { compareDocuments, type DraftStats } from "../../logic/comparison";

type Compared = {
  left: string;
  right: string;
  result: ReturnType<typeof compareDocuments>;
};

const stats = (s: DraftStats) =>
  `${s.words.toLocaleString()} words · ${s.paragraphs} paragraphs · ${s.averageSentenceWords} words/sentence`;

export function CompareDialog({
  at,
  rows,
  open,
  onOpenChange,
}: {
  at: SectionAddress;
  rows: DraftRow[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { api } = useDeps();
  const [left, setLeft] = useState(rows[0]?.id ?? "");
  const [right, setRight] = useState(rows[1]?.id ?? rows[0]?.id ?? "");
  const [compared, setCompared] = useState<Compared | null>(null);
  const [state, setState] = useState<{ busy: boolean; error: string | null }>({
    busy: false,
    error: null,
  });
  const label = (row: DraftRow) => `${row.name}${row.primary ? " (Primary)" : ""}`;
  const name = (id: string) => rows.find((row) => row.id === id)?.name ?? id;

  const compare = async () => {
    setState({ busy: true, error: null });
    try {
      const [a, b] = await Promise.all([api.draft(at, left), api.draft(at, right)]);
      setCompared({ left, right, result: compareDocuments(a.document, b.document) });
      setState({ busy: false, error: null });
    } catch (error) {
      setState({
        busy: false,
        error: messageOf(error, "The drafts could not be compared."),
      });
    }
  };

  const picker = (value: string, onChange: (id: string) => void, which: string) => (
    <select
      className="st-input st-input-sm"
      aria-label={which}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {rows.map((row) => (
        <option key={row.id} value={row.id}>
          {label(row)}
        </option>
      ))}
    </select>
  );

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Compare drafts"
      wide
      className="lw-dialog lw-compare"
    >
      <div className="lw-compare-pickers">
        {picker(left, setLeft, "First draft")}
        {picker(right, setRight, "Second draft")}
        <Button variant="primary" size="sm" busy={state.busy} onClick={compare}>
          Compare
        </Button>
      </div>
      {state.error ? <p className="st-error-text">{state.error}</p> : null}
      {compared ? (
        <div className="lw-compare-results">
          <div className="lw-compare-stats">
            <span>
              <strong>{name(compared.left)}</strong> {stats(compared.result.left)}
            </span>
            <span>
              <strong>{name(compared.right)}</strong> {stats(compared.result.right)}
            </span>
          </div>
          <div className="lw-compare-grid">
            {compared.result.rows.flatMap((row) => [
              <p
                key={`${row.id}-l`}
                className={`lw-compare-block ${row.left ? row.status : "absent"}`}
              >
                {row.left || "— not in this draft —"}
              </p>,
              <p
                key={`${row.id}-r`}
                className={`lw-compare-block ${row.right ? row.status : "absent"}`}
              >
                {row.right || "— not in this draft —"}
              </p>,
            ])}
          </div>
        </div>
      ) : (
        <p className="lw-muted">
          Pick two drafts. Paragraphs they share line up, and changed ones are marked.
        </p>
      )}
    </Modal>
  );
}
