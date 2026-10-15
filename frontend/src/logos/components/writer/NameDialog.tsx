// Asking for a name -- a new draft's, a rename, a new chapter's title -- as a
// promise: `await ask("Name the new draft", "Draft 2")` is the name, or null.

import { useCallback, useRef, useState, type ReactNode } from "react";
import { Button } from "../../../components/ui/Button";
import { Modal } from "../../../components/ui/Modal";

interface Asking {
  heading: string;
  value: string;
  label: string;
  resolve: (name: string | null) => void;
}

export type AskName = (
  heading: string,
  value?: string,
  label?: string,
) => Promise<string | null>;

export function useNameDialog(): [AskName, ReactNode] {
  const [asking, setAsking] = useState<Asking | null>(null);
  const ask = useCallback<AskName>(
    (heading, value = "", label = "Draft name") =>
      new Promise((resolve) => setAsking({ heading, value, label, resolve })),
    [],
  );
  const finish = (name: string | null) => {
    asking?.resolve(name);
    setAsking(null);
  };
  const dialog = asking ? (
    <NameDialog key={asking.heading} asking={asking} onFinish={finish} />
  ) : null;
  return [ask, dialog];
}

function NameDialog({
  asking,
  onFinish,
}: {
  asking: Asking;
  onFinish: (name: string | null) => void;
}) {
  const [value, setValue] = useState(asking.value);
  const input = useRef<HTMLInputElement>(null);
  const name = value.trim();
  return (
    <Modal
      open
      onOpenChange={(open) => !open && onFinish(null)}
      title={asking.heading}
      className="lw-dialog"
      footer={
        <>
          <Button variant="ghost" onClick={() => onFinish(null)}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="lw-name-form" disabled={!name}>
            Continue
          </Button>
        </>
      }
    >
      <form
        id="lw-name-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (name) onFinish(name);
        }}
      >
        <input
          ref={input}
          className="st-input lw-name-input"
          aria-label={asking.label}
          maxLength={120}
          value={value}
          autoFocus
          onFocus={(event) => event.currentTarget.select()}
          onChange={(event) => setValue(event.target.value)}
        />
      </form>
    </Modal>
  );
}
