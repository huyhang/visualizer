import { useState, type FormEvent, type KeyboardEvent } from "react";
import type { AskRequest } from "../../api/types";
import {
  askRequest,
  DEFAULT_OPTIONS,
  parseLanguages,
  questionProblem,
  type AskOptions,
} from "../../logic/ask";
import { Button } from "../ui/Button";
import { AutoTextarea } from "../ui/AutoTextarea";
import { AskOptionsMenu } from "./AskOptions";

/**
 * Where every line of inquiry starts. Enter asks, Shift+Enter breaks the line.
 * The settings live behind the cog and are kept between questions.
 */
export function AskBox({
  canSubmit,
  unavailable,
  busy,
  error,
  onAsk,
}: {
  canSubmit: boolean;
  unavailable: string | null;
  busy: boolean;
  error: string | null;
  onAsk: (request: AskRequest) => Promise<unknown>;
}) {
  const [question, setQuestion] = useState("");
  const [options, setOptions] = useState<AskOptions>(DEFAULT_OPTIONS);
  const problem = questionProblem(question);
  const languagesOk = Array.isArray(parseLanguages(options.languages));
  const ready = canSubmit && !problem && languagesOk && !busy;

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!ready) return;
    try {
      await onAsk(askRequest(question, options));
      setQuestion("");
    } catch {
      /* the error is shown below; the question stays for another try */
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <form className="st-ask" onSubmit={submit} aria-label="Ask the researcher">
      <AutoTextarea
        className="st-ask-input"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="What do you want to know?"
        aria-label="Research question"
        maxRows={6}
        maxLength={500}
        rows={2}
      />
      <div className="st-ask-bar">
        <span className="st-ask-hint">
          {unavailable ??
            (options.reviewPlan ? "You'll check the search plan first" : "Enter to ask")}
        </span>
        <AskOptionsMenu options={options} onChange={setOptions} />
        <Button
          variant="primary"
          size="sm"
          type="submit"
          icon="sparkle"
          busy={busy}
          disabled={!ready}
        >
          Research
        </Button>
      </div>
      {error ? (
        <p className="st-error-text" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
