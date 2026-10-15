// "Show me that scene": scroll to it and flash it when it is on this screen,
// and open it beside the screen when it is not. The cross-thread case is the
// one worth reaching -- a conflict with a thread you were not looking at is the
// thing you could not have found any other way.

import { useCallback, useRef } from "react";

const FLASH_MS = 1200;

/** The element drawing `scene` inside `root`, matched by value rather than by selector. */
export function sceneElement(
  root: ParentNode | null,
  scene: string,
): HTMLElement | undefined {
  if (!root) return undefined;
  return Array.from(root.querySelectorAll<HTMLElement>("[data-event]")).find(
    (el) => el.dataset.event === scene,
  );
}

export function useJump(onElsewhere: (scene: string) => void) {
  const container = useRef<HTMLDivElement>(null);
  const jump = useCallback(
    (scene: string) => {
      const target = sceneElement(container.current, scene);
      if (!target) {
        onElsewhere(scene);
        return;
      }
      target.scrollIntoView({ block: "center", behavior: "smooth" });
      target.classList.add("is-flash");
      setTimeout(() => target.classList.remove("is-flash"), FLASH_MS);
    },
    [onElsewhere],
  );
  return { container, jump };
}
