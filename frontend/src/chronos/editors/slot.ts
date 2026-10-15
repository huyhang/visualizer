// What an editor area adds to the workspace: the actions that open it, and
// the dialog itself, mounted once beside the screens.

import type { ReactNode } from "react";
import type { WorkspaceActions } from "../components/shell/Actions";

export interface EditorSlot {
  actions: Partial<WorkspaceActions>;
  element: ReactNode;
}

export const EMPTY_SLOT: EditorSlot = { actions: {}, element: null };
