import { useState } from "react";
import type { SourceRow } from "../../api/types";
import { isInboxRef } from "../../logic/citations";
import { siteOf } from "../../logic/format";
import { Button } from "../ui/Button";
import { AutoTextarea } from "../ui/AutoTextarea";
import { Modal } from "../ui/Modal";

const MAX_FEEDBACK = 2000;

/**
 * Research the same question again, steered: what to change, and which pages
 * never to read again. The new version replaces this draft; the old one stays
 * in its history.
 */
export function SteerDialog({
  sources,
  distrusted,
  busy,
  error,
  onSubmit,
  onClose,
}: {
  sources: SourceRow[];
  distrusted: string[];
  busy: boolean;
  error: string | null;
  onSubmit: (feedback: string, exclude: string[]) => void;
  onClose: () => void;
}) {
  const [feedback, setFeedback] = useState("");
  const [exclude, setExclude] = useState<Set<string>>(new Set(distrusted));
  const steerable = sources.filter((s) => isInboxRef(s.ref));
  const toggle = (ref: string) => {
    const next = new Set(exclude);
    if (next.has(ref)) next.delete(ref);
    else next.add(ref);
    setExclude(next);
  };
  const ok = feedback.trim().length > 0 && feedback.length <= MAX_FEEDBACK;

  return (
    <Modal
      open
      wide
      onOpenChange={(open) => !open && onClose()}
      title="Steer this draft"
      description="The researcher reads the kept pages again, checks every quote anew, and searches for more. Your feedback can end up in its web searches."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            icon="steer"
            busy={busy}
            disabled={!ok}
            onClick={() => onSubmit(feedback.trim(), [...exclude])}
          >
            Research again
          </Button>
        </>
      }
    >
      <label className="st-field">
        <span>What should change?</span>
        <AutoTextarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="Focus on how ordinary people drank tea, not the court."
          maxRows={8}
          maxLength={MAX_FEEDBACK}
          autoFocus
        />
      </label>
      {steerable.length ? (
        <fieldset className="st-field st-steer-sources">
          <legend>Pages not to read again</legend>
          {steerable.map((source) => (
            <label key={source.ref} className="st-check">
              <input
                type="checkbox"
                checked={exclude.has(source.ref)}
                onChange={() => toggle(source.ref)}
              />
              <span>
                <strong>{source.title}</strong>
                <small>{siteOf(source.url)}</small>
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}
      {error ? (
        <p className="st-error-text" role="alert">
          {error}
        </p>
      ) : null}
    </Modal>
  );
}
