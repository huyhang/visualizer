// Whether the workspace has room for three columns (`logic/layout.ts`),
// re-measured as it is resized and when the shared text size changes.
//
// Measured here rather than by a CSS container query: a query container
// applies layout containment, which would make the workspace the containing
// block of its own fixed drawers, backdrop and formatting bar.

import { useLayoutEffect, useState, type RefObject } from "react";
import { usesDrawers } from "../logic/layout";

const remPixels = () =>
  parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;

/** Null until the workspace has been measured, which happens before it is first painted. */
export function useDrawerLayout(workspace: RefObject<HTMLElement | null>): boolean | null {
  const [drawers, setDrawers] = useState<boolean | null>(null);
  useLayoutEffect(() => {
    const element = workspace.current;
    if (!element) return;
    const measure = () =>
      setDrawers(usesDrawers(element.getBoundingClientRect().width, remPixels()));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    // prefs.js announces a new text size this way.
    document.addEventListener("prefs:fontscale", measure);
    return () => {
      observer.disconnect();
      document.removeEventListener("prefs:fontscale", measure);
    };
  }, [workspace]);
  return drawers;
}
