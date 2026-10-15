// What the workspace can start from anywhere -- the palette, a keyboard
// shortcut, an empty state: write a new thread, scene, goal or book. The
// editors register themselves here, so whoever offers "New scene" does not
// need to know how a scene is written.

import { createContext, useContext, type ReactNode } from "react";
import type { SceneEvent } from "../../api/types";

/** How a caller hears that the scene it opened was saved: the thread editor adds it. */
export interface SceneEditOptions {
  onSaved?: (scene: SceneEvent) => void;
}

export interface WorkspaceActions {
  newThread?: () => void;
  newScene?: (options?: SceneEditOptions) => void;
  newGoal?: () => void;
  newBook?: () => void;
  editThread?: (id: string) => void;
  editScene?: (id: string, options?: SceneEditOptions) => void;
  editGoal?: (id: string) => void;
  editBook?: () => void;
}

const ActionsContext = createContext<WorkspaceActions>({});

export function ActionsProvider({
  actions,
  children,
}: {
  actions: WorkspaceActions;
  children: ReactNode;
}) {
  return <ActionsContext.Provider value={actions}>{children}</ActionsContext.Provider>;
}

export function useActions(): WorkspaceActions {
  return useContext(ActionsContext);
}
