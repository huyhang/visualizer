// Whether the workspace is laid out for a phone: the width at which the
// sidebar becomes a strip of tabs above the screen and the shared nav a bar
// along the bottom (styles/shell.css, service-nav.css). Asked of the same media
// query those stylesheets use, so what is rendered and how it is drawn agree.

import { useSyncExternalStore } from "react";

export const NARROW = "(max-width: 820px)";

export function useNarrow(query: string = NARROW): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
