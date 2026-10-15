// The workspace's editors, mounted once beside the screens: whichever is open
// floats over the page, and closing it puts you back exactly where you were.
// Each area registers how it is opened in the workspace's actions, so a
// screen offering "New scene" does not need to know how a scene is written.

import { Fragment, type ReactNode } from "react";
import { useBookEditors } from "../../editors/book/register";
import { useGoalEditors } from "../../editors/goal/register";
import { useSceneEditors } from "../../editors/scene/register";
import { useThreadEditors } from "../../editors/thread/register";
import { ActionsProvider, type WorkspaceActions } from "./Actions";

export function Editors({ children }: { children: ReactNode }) {
  const slots = [useThreadEditors(), useSceneEditors(), useGoalEditors(), useBookEditors()];
  const actions: WorkspaceActions = Object.assign({}, ...slots.map((s) => s.actions));
  return (
    <ActionsProvider actions={actions}>
      {children}
      {slots.map((s, n) => (
        <Fragment key={n}>{s.element}</Fragment>
      ))}
    </ActionsProvider>
  );
}
