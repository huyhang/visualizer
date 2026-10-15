// Talking an issue over with the editor who raised it. The writer answers --
// "that's deliberate", "why?", "what would you do instead?" -- and the
// editor replies, saying whether it maintains, revises or withdraws the note.
// A reply never changes the issue's status: the writer decides.

import { useState } from "react";
import { messageOf } from "../../api/errors";
import type { ReviewIssue, Turn } from "../../api/types";
import { Button } from "../../../components/ui/Button";
import { Spinner } from "../../../components/ui/Spinner";
import { isReplying, STANCE_LABELS, stageLabel } from "../../logic/review";
import { FixPreview } from "./FixPreview";

const MAX_CHARS = 2000;
const MAX_MESSAGES = 10;
const PROMPTS = ["That’s deliberate.", "Why does it matter?", "What would you do instead?"];

function TurnView({ turn, quote }: { turn: Turn; quote: string }) {
  if (turn.role === "writer") {
    return (
      <li className="lw-turn lw-turn-writer">
        <p>{turn.text}</p>
      </li>
    );
  }
  return (
    <li className="lw-turn lw-turn-editor">
      {turn.stance ? (
        <span className={`lw-stance lw-stance-${turn.stance}`}>
          {STANCE_LABELS[turn.stance]}
        </span>
      ) : null}
      <p>{turn.text}</p>
      {turn.replacement ? (
        <FixPreview quote={quote} replacement={turn.replacement} />
      ) : null}
      {turn.suggestion && !turn.replacement ? (
        <p className="lw-suggestion">{turn.suggestion}</p>
      ) : null}
    </li>
  );
}

export function Discussion({
  issue,
  onSend,
}: {
  issue: ReviewIssue;
  /** Post a message; rejects, with the reason, if it was not taken. */
  onSend: (text: string) => Promise<void>;
}) {
  const [text, setText] = useState("");
  // This issue's own: a message that failed on one issue says nothing on another.
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const replying = isReplying(issue);
  const used = issue.discussion.filter((turn) => turn.role === "writer").length;
  const full = used >= MAX_MESSAGES;
  const busy = replying || sending;
  const send = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed || busy || full) return;
    setSending(true);
    setError(null);
    try {
      await onSend(trimmed);
      setText(""); // only once it is taken: a refused message stays to send again
    } catch (failure) {
      setError(messageOf(failure, "The message could not be sent."));
    } finally {
      setSending(false);
    }
  };
  return (
    <section className="lw-discussion" aria-label="Discussion with the editor">
      <h3 className="lw-section-title">Discussion</h3>
      {issue.discussion.length ? (
        <ol className="lw-thread">
          {issue.discussion.map((turn, index) => (
            <TurnView key={index} turn={turn} quote={issue.quote} />
          ))}
        </ol>
      ) : (
        <p className="lw-muted lw-small">
          Answer the editor: explain a choice, ask why, or ask for another fix.
        </p>
      )}
      {replying ? (
        <p className="lw-replying" role="status">
          <Spinner size={13} /> {stageLabel(issue.reply!.state, issue.reply!.progress)}…
        </p>
      ) : null}
      {issue.reply?.state === "failed" ? (
        <p className="st-error-text">
          {issue.reply.error?.message ?? "The editor could not reply."} Send another message
          to ask again.
        </p>
      ) : null}
      {error ? <p className="st-error-text">{error}</p> : null}
      {full ? (
        <p className="lw-muted lw-small">
          This discussion has its {MAX_MESSAGES} messages. A fresh review of the passage
          will serve better.
        </p>
      ) : (
        <>
          {!issue.discussion.length ? (
            <div className="lw-prompts">
              {PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="lw-prompt"
                  disabled={busy}
                  onClick={() => void send(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          ) : null}
          <form
            className="lw-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void send(text);
            }}
          >
            <textarea
              className="st-textarea"
              rows={2}
              maxLength={MAX_CHARS}
              placeholder="Reply to the editor…"
              aria-label="Reply to the editor"
              value={text}
              disabled={busy}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  void send(text);
                }
              }}
            />
            <Button
              type="submit"
              size="sm"
              variant="primary"
              icon="send"
              disabled={!text.trim() || busy}
              busy={sending}
            >
              Send
            </Button>
          </form>
        </>
      )}
    </section>
  );
}
