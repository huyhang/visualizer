import { useEffect } from "react";
import { keyboardCover } from "../logic/layout";

/**
 * Keep `--lw-keyboard` equal to how much of the window a phone's on-screen
 * keyboard covers (`logic/layout.ts`), so the formatting bar docked at the foot
 * of the screen rides above it instead of hiding behind it. Measured again
 * whenever either viewport changes: the window's own size moves too, as when
 * the first layout settles or the phone turns.
 */
export function useKeyboardOffset(root: HTMLElement = document.documentElement) {
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const place = () => {
      const covered = keyboardCover({
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        width: viewport.width,
        height: viewport.height,
        offsetTop: viewport.offsetTop,
        scale: viewport.scale,
      });
      root.style.setProperty("--lw-keyboard", `${covered}px`);
    };
    viewport.addEventListener("resize", place);
    viewport.addEventListener("scroll", place);
    window.addEventListener("resize", place);
    place();
    return () => {
      viewport.removeEventListener("resize", place);
      viewport.removeEventListener("scroll", place);
      window.removeEventListener("resize", place);
    };
  }, [root]);
}
