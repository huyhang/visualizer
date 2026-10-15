// The panel on the right: whatever was opened beside the page, with Back for
// the links followed inside it. Closes on Escape; the page behind keeps its
// place the whole time.

import { useEffect } from "react";
import { targetKey, type InspectorTarget } from "../../logic/inspector";
import { useOptionalBookScope } from "../shell/BookScope";
import { useInspector } from "../shell/InspectorContext";
import { ArticlePane } from "./ArticlePane";
import { GoalPane } from "./GoalPane";
import { ScenePane } from "./ScenePane";
import { ThreadPane } from "./ThreadPane";
import { IconButton } from "../../../components/ui/Button";

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

export function Inspector() {
  const { target, canGoBack, back, close } = useInspector();
  const scope = useOptionalBookScope();
  useEffect(() => {
    if (!target) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.querySelector("[role=dialog]")) close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [target, close]);
  if (!target || !scope) return null;
  return (
    <aside className="cw-inspector" aria-label="Details">
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
