// The draft session (`logic/draftSession.ts`) for the page: created once,
// read through `useSyncExternalStore`, and told when the tab is closing,
// hidden or back online.

import { useEffect, useState, useSyncExternalStore } from "react";
import { useDeps } from "../deps";
import { createDraftSession, type EditorReader } from "../logic/draftSession";
import type { Workspace } from "./useWorkspace";

export type { EditorReader, SaveStatus } from "../logic/draftSession";

export function useDraftSession(workspace: Workspace, reader: EditorReader) {
  const { api, recovery, timer, navigate, user } = useDeps();
  const [session] = useState(() =>
    createDraftSession(workspace, { api, recovery, timer, navigate, user, reader }),
  );
  const state = useSyncExternalStore(session.subscribe, session.getState);

  useEffect(() => session.resume(), [session]);

  // Leaving, hiding or losing the tab writes what is pending; coming back online retries.
  useEffect(() => {
    const urgent = () => session.actions.flushUrgently();
    const hidden = () => document.visibilityState === "hidden" && urgent();
    const online = () => session.actions.saveNow();
    window.addEventListener("pagehide", urgent);
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("pagehide", urgent);
      document.removeEventListener("visibilitychange", hidden);
      window.removeEventListener("online", online);
    };
  }, [session]);

  return {
    ...state,
    changed: session.changed,
    setTitle: session.setTitle,
    actions: session.actions,
  };
}
