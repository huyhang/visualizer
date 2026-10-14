import { useState } from "react";
import { MAX_QUESTION, questionProblem } from "../../logic/ask";
import { Button } from "../ui/Button";
import { AutoTextarea } from "../ui/AutoTextarea";
import { Modal } from "../ui/Modal";

/**
 * A sub-topic, worded from the passage. It becomes a new question under this
 * topic; the draft it came from stays exactly as it is.
 */
export function DigDeeperDialog({
  initial,
  parentTitle,
  busy,
  error,
  onSubmit,
  onClose,
}: {
  initial: string;
  parentTitle: string;
  busy: boolean;
  error: string | null;
  onSubmit: (question: string) => void;
  onClose: () => void;
}) {
  const [question, setQuestion] = useState(initial);
  const problem = questionProblem(question);
  return (
    <Modal
      open
      onOpenChange={(open) => !open && onClose()}
      title="Dig deeper"
      description={
        <>
          A new topic under <strong>{parentTitle}</strong>. Make the question your own — it
          is the only thing the researcher searches with.
        </>
      }
      footer={
        <>
          <span className={`st-counter${question.length > MAX_QUESTION ? " is-over" : ""}`}>
            {question.length}/{MAX_QUESTION}
          </span>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            icon="sparkle"
            busy={busy}
            disabled={!!problem}
            onClick={() => onSubmit(question.trim())}
          >
            Research
          </Button>
        </>
      }
    >
      <AutoTextarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        aria-label="Question for the sub-topic"
        maxRows={10}
        autoFocus
        onFocus={(e) => e.currentTarget.select()}
      />
      {error ? (
        <p className="st-error-text" role="alert">
          {error}
        </p>
      ) : null}
    </Modal>
  );
}
