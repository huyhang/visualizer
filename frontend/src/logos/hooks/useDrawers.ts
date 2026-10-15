// The outline and the writing tools become drawers below 1100px. One opens at
// a time; Escape or the backdrop closes it and focus goes back to the button
// that opened it. While one is open the page behind it does not scroll.

import { useCallback, useEffect, useRef, useState } from "react";

export type Drawer = "outline" | "tools";

export function useDrawers() {
  const [open, setOpen] = useState<Drawer | null>(null);
  const trigger = useRef<HTMLElement | null>(null);

  const close = useCallback((restoreFocus = true) => {
    setOpen(null);
    if (restoreFocus) trigger.current?.focus({ preventScroll: true });
    trigger.current = null;
  }, []);

  const show = useCallback((drawer: Drawer) => {
    if (document.activeElement instanceof HTMLElement)
      trigger.current = document.activeElement;
    setOpen(drawer);
  }, []);

  const toggle = useCallback(
    (drawer: Drawer) => (open === drawer ? close() : show(drawer)),
    [open, close, show],
  );

  useEffect(() => {
    document.body.classList.toggle("lw-drawer-open", open !== null);
    if (!open) return;
    const escape = (event: KeyboardEvent) => event.key === "Escape" && close();
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [open, close]);

  return { open, show, toggle, close };
}
