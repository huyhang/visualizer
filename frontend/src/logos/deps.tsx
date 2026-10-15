// Everything the writing page depends on that is not React: the API, where
// unsaved words are kept, what the browser remembers, time, ids, navigation and
// whether the tab is being looked at. `main.tsx` builds the real ones; tests
// build fakes. Nothing below imports a browser global for any of these.

import { createContext, useContext, type ReactNode } from "react";
import type { LogosApi } from "./api/LogosApi";
import type { IdFactory } from "./doc/ids";
import type { Timer } from "./logic/autosave";
import type { Preferences } from "./logic/preferences";
import type { RecoveryStore } from "./logic/recovery";

export interface Visibility {
  visible: () => boolean;
  subscribe: (onChange: () => void) => () => void;
}

export interface WriterDeps {
  api: LogosApi;
  recovery: RecoveryStore;
  preferences: Preferences;
  timer: Timer;
  makeId: IdFactory;
  /** Leave the page for `url`. */
  navigate: (url: string) => void;
  /** Open `url` in a new tab, leaving this page as it is. */
  openTab: (url: string) => void;
  visibility: Visibility;
  user: string;
}

const DepsContext = createContext<WriterDeps | null>(null);

export function WriterDepsProvider({
  deps,
  children,
}: {
  deps: WriterDeps;
  children: ReactNode;
}) {
  return <DepsContext.Provider value={deps}>{children}</DepsContext.Provider>;
}

export function useDeps(): WriterDeps {
  const deps = useContext(DepsContext);
  if (!deps) throw new Error("useDeps() needs a <WriterDepsProvider> above it.");
  return deps;
}

/** The document's own visibility, for polling faster while someone is looking. */
export const documentVisibility: Visibility = {
  visible: () => document.visibilityState !== "hidden",
  subscribe: (onChange) => {
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  },
};
