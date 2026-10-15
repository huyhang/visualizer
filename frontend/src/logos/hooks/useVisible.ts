import { useSyncExternalStore } from "react";
import type { Visibility } from "../deps";

/** Whether the page is being looked at, from an injected source. */
export function useVisible(visibility: Visibility): boolean {
  return useSyncExternalStore(visibility.subscribe, visibility.visible, () => true);
}
