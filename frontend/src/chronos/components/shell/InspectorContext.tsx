// The inspector's state, shared: any view can open something beside itself.

import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react";
import { inspectorReducer, type InspectorTarget } from "../../logic/inspector";

export interface InspectorControls {
  /** What is on screen, or null when the panel is shut. */
  target: InspectorTarget | null;
  canGoBack: boolean;
  /** Show `target`, forgetting the trail. */
  open: (target: InspectorTarget) => void;
  /** Follow a link from what is showing; Back returns to it. */
  push: (target: InspectorTarget) => void;
  back: () => void;
  close: () => void;
  /** Take a deleted record out of the trail, wherever it is. */
  forget: (target: InspectorTarget) => void;
}

const InspectorContext = createContext<InspectorControls | null>(null);

export function InspectorProvider({
  initial = [],
  children,
}: {
  /** What it starts on: a peek opens straight onto its subject. */
  initial?: InspectorTarget[];
  children: ReactNode;
}) {
  const [stack, dispatch] = useReducer(inspectorReducer, initial);
  // The verbs never change, so a screen can depend on them without re-running.
  const verbs = useMemo(
    () => ({
      open: (target: InspectorTarget) => dispatch({ type: "open", target }),
      push: (target: InspectorTarget) => dispatch({ type: "push", target }),
      back: () => dispatch({ type: "back" }),
      close: () => dispatch({ type: "close" }),
      forget: (target: InspectorTarget) => dispatch({ type: "forget", target }),
    }),
    [],
  );
  const controls = useMemo<InspectorControls>(
    () => ({
      target: stack[stack.length - 1] ?? null,
      canGoBack: stack.length > 1,
      ...verbs,
    }),
    [stack, verbs],
  );
  return <InspectorContext.Provider value={controls}>{children}</InspectorContext.Provider>;
}

export function useInspector(): InspectorControls {
  const controls = useContext(InspectorContext);
  if (!controls) throw new Error("useInspector() needs an <InspectorProvider> above it.");
  return controls;
}
