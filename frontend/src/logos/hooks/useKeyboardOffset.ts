import { useEffect } from "react";

/**
 * Keep `--lw-keyboard` equal to how much of the window a phone's on-screen
 * keyboard covers, so the formatting bar docked at the foot of the screen
 * rides above it instead of hiding behind it.
 */
export function useKeyboardOffset(root: HTMLElement = document.documentElement) {
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const place = () => {
      const covered = Math.max(
        0,
        window.innerHeight - viewport.height - viewport.offsetTop,
      );
      root.style.setProperty("--lw-keyboard", `${Math.round(covered)}px`);
    };
    viewport.addEventListener("resize", place);
    viewport.addEventListener("scroll", place);
    place();
    return () => {
      viewport.removeEventListener("resize", place);
      viewport.removeEventListener("scroll", place);
    };
  }, [root]);
}
