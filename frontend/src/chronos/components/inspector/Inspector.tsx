// The panel on the right: whatever was opened beside the page, with Back for
// the links followed inside it. Closes on Escape; the page behind keeps its
// place the whole time. Over a dialog, where a panel beside the page could
// not be reached, the same panes open in a peek on top instead.

import { useEffect, useRef } from "react";
import { topDialog } from "../common/layers";
import { targetKey, type InspectorTarget } from "../../logic/inspector";
import { useOptionalBookScope } from "../shell/BookScope";
import { InspectorProvider, useInspector } from "../shell/InspectorContext";
import { ArticlePane } from "./ArticlePane";
import { GoalPane } from "./GoalPane";
import { ScenePane } from "./ScenePane";
import { ThreadPane } from "./ThreadPane";
import { IconButton } from "../../../components/ui/Button";
import { Modal } from "../../../components/ui/Modal";

function Pane({ target, book }: { target: InspectorTarget; book: string }) {
  switch (target.kind) {
    case "scene":
      return <ScenePane id={target.id} />;
    case "goal":
      return <GoalPane id={target.id} />;
    case "thread":
      return <ThreadPane id={target.id} />;
    case "article":
      return <ArticlePane book={book} entity={target.ref} />;
  }
}

/**
 * The keyboard follows the panel: in when it opens, kept in it as one subject
 * replaces another, and back to whatever opened it when it closes -- unless
 * the writer has already gone somewhere else.
 */
function usePanelFocus(open: boolean, subject: string | null) {
  const panel = useRef<HTMLElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const before = document.activeElement;
    returnTo.current =
      before instanceof HTMLElement && before !== document.body ? before : null;
    panel.current?.focus({ preventScroll: true });
    return () => {
      const now = document.activeElement;
      if (now && now !== document.body) return;
      const back = returnTo.current?.isConnected ? returnTo.current : null;
      (back ?? document.getElementById("cw-main"))?.focus({ preventScroll: true });
    };
  }, [open]);
  useEffect(() => {
    // A new subject redraws the body, and whatever in it had focus with it.
    const now = document.activeElement;
    if (subject && (!now || now === document.body))
      panel.current?.focus({ preventScroll: true });
  }, [subject]);
  return panel;
}

export function Inspector() {
  const { target, canGoBack, back, close } = useInspector();
  const scope = useOptionalBookScope();
  const panel = usePanelFocus(Boolean(target && scope), target ? targetKey(target) : null);
  useEffect(() => {
    if (!target) return;
    // Only an Escape nothing else took: a dialog, menu or list over the page
    // closes on it first and marks it handled, and the panel stays.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented && !topDialog()) close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [target, close]);
  if (!target || !scope) return null;
  return (
    <aside ref={panel} className="cw-inspector" aria-label="Details" tabIndex={-1}>
      <div className="cw-inspector-bar">
        {canGoBack ? <IconButton icon="arrowLeft" label="Back" onClick={back} /> : <span />}
        <IconButton icon="x" label="Close the panel" onClick={close} />
      </div>
      <div className="cw-inspector-body" key={targetKey(target)}>
        <Pane target={target} book={scope.id} />
      </div>
    </aside>
  );
}

const KINDS: Record<InspectorTarget["kind"], string> = {
  scene: "Scene",
  goal: "Goal",
  thread: "Thread",
  article: "Article",
};

function PeekBody() {
  const { target, canGoBack, back } = useInspector();
  const scope = useOptionalBookScope();
  if (!target || !scope) return null;
  return (
    <div className="cw-peek">
      {canGoBack ? (
        <div className="cw-inspector-bar">
          <IconButton icon="arrowLeft" label="Back" onClick={back} />
        </div>
      ) : null}
      <div className="cw-inspector-body" key={targetKey(target)}>
        <Pane target={target} book={scope.id} />
      </div>
    </div>
  );
}

/** `target` in a dialog of its own, over the one open: its links stack inside it. */
export function InspectorPeek({
  target,
  onClose,
}: {
  target: InspectorTarget;
  onClose: () => void;
}) {
  return (
    <Modal open onOpenChange={(open) => !open && onClose()} title={KINDS[target.kind]}>
      <InspectorProvider initial={[target]}>
        <PeekBody />
      </InspectorProvider>
    </Modal>
  );
}
