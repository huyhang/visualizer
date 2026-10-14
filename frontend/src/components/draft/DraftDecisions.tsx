import { useState } from "react";
import { Button } from "../ui/Button";
import type { IconName } from "../ui/Icon";
import { Modal } from "../ui/Modal";

export type Decision = "keep" | "done" | "discard";

/** What deciding a draft's fate can do, each a promise the studio fulfils. */
export interface DraftDecisionHandlers {
  pending: Record<Decision, boolean>;
  decide: (decision: Decision) => void;
}

interface Choice {
  label: string;
  icon: IconName;
  variant: "secondary" | "ghost";
  title: string;
  /** What happens, told differently once some of the draft is in notes. */
  explain: (inNotes: boolean) => string;
  confirm: string;
  confirmVariant: "primary" | "danger";
}

const CHOICES: Record<Decision, Choice> = {
  keep: {
    label: "Keep as note",
    icon: "note",
    variant: "secondary",
    title: "Keep the whole draft as a note?",
    explain: () =>
      "It becomes a verified research note in your world, with all its sources. The draft leaves the inbox.",
    confirm: "Keep as note",
    confirmVariant: "primary",
  },
  done: {
    label: "Done with it",
    icon: "check",
    variant: "secondary",
    title: "Done with this draft?",
    explain: (inNotes) =>
      inNotes
        ? "It leaves the inbox. The notes you saved from it keep their text and sources."
        : "Nothing from it is in a note yet. It leaves the inbox, and its sources go with it.",
    confirm: "Close the draft",
    confirmVariant: "primary",
  },
  discard: {
    label: "Discard",
    icon: "trash",
    variant: "ghost",
    title: "Discard this draft?",
    explain: () =>
      "The draft and the sources only it found are removed from the inbox. Notes you already saved keep everything they took.",
    confirm: "Discard",
    confirmVariant: "danger",
  },
};

const ORDER: Decision[] = ["keep", "done", "discard"];

/** The three ways a draft leaves the inbox, each asked about before it happens. */
export function DraftDecisions({
  inNotes,
  handlers,
}: {
  inNotes: boolean;
  handlers: DraftDecisionHandlers;
}) {
  const [confirming, setConfirming] = useState<Decision | null>(null);
  const choice = confirming ? CHOICES[confirming] : null;

  return (
    <>
      {ORDER.map((decision) => (
        <Button
          key={decision}
          size="sm"
          variant={CHOICES[decision].variant}
          icon={CHOICES[decision].icon}
          busy={handlers.pending[decision]}
          onClick={() => setConfirming(decision)}
        >
          {CHOICES[decision].label}
        </Button>
      ))}
      <Modal
        open={choice !== null}
        onOpenChange={(open) => !open && setConfirming(null)}
        title={choice?.title ?? ""}
        description={choice?.explain(inNotes)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirming(null)}>
              Cancel
            </Button>
            <Button
              variant={choice?.confirmVariant ?? "primary"}
              onClick={() => {
                setConfirming(null);
                if (confirming) handlers.decide(confirming);
              }}
            >
              {choice?.confirm}
            </Button>
          </>
        }
      />
    </>
  );
}
