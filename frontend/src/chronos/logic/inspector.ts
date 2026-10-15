// What the inspector panel is showing, and how to get back from it.
//
// The inspector replaces the classic page's peek card and most of its modals:
// a scene, goal, thread or Akasha article opens beside whatever you were
// reading, so you keep your place. Following a link inside it -- the scene's
// character, the goal's delivering scene -- stacks, and Back unwinds.

import type { EntityRef } from "../api/types";

export type InspectorTarget =
  | { kind: "scene"; id: string }
  | { kind: "goal"; id: string }
  | { kind: "thread"; id: string }
  | { kind: "article"; ref: EntityRef };

export type InspectorAction =
  | { type: "open"; target: InspectorTarget }
  | { type: "push"; target: InspectorTarget }
  | { type: "back" }
  | { type: "close" }
  /** Something was deleted: it leaves the trail wherever it is in it. */
  | { type: "forget"; target: InspectorTarget };

export function sameTarget(a: InspectorTarget, b: InspectorTarget): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "article" && b.kind === "article") {
    return (
      a.ref.database === b.ref.database &&
      a.ref.collection === b.ref.collection &&
      a.ref.id === b.ref.id
    );
  }
  return "id" in a && "id" in b && a.id === b.id;
}

/** The trail of what was opened; the last entry is on screen. */
export function inspectorReducer(
  stack: InspectorTarget[],
  action: InspectorAction,
): InspectorTarget[] {
  switch (action.type) {
    case "open":
      return [action.target];
    case "push": {
      const top = stack[stack.length - 1];
      return top && sameTarget(top, action.target) ? stack : [...stack, action.target];
    }
    case "back":
      return stack.length ? stack.slice(0, -1) : stack;
    case "close":
      return stack.length ? [] : stack;
    case "forget": {
      const kept = stack.filter((t) => !sameTarget(t, action.target));
      return kept.length === stack.length ? stack : kept;
    }
  }
}

/** A stable key for a target, for React and for tests. */
export function targetKey(target: InspectorTarget): string {
  return target.kind === "article"
    ? `article:${target.ref.database}/${target.ref.collection}/${target.ref.id}`
    : `${target.kind}:${target.id}`;
}
