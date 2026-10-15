// The manuscript's own right-click menu. Shown only when there is something
// manuscript-specific to offer -- selected words, or a linked phrase -- so the
// browser's menu, with paste and the spellchecker's suggestions, survives
// everywhere else. That policy is the caller's; this renders, places and closes.

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { menuPosition } from "../../logic/menu";

export interface MenuAction {
  label: string;
  run: () => void;
}

export interface MenuRequest {
  x: number;
  y: number;
  actions: MenuAction[];
}

export function ContextMenu({
  request,
  onClose,
}: {
  request: MenuRequest | null;
  onClose: () => void;
}) {
  const node = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    if (!request || !node.current) return setPlace(null);
    setPlace(
      menuPosition(
        { x: request.x, y: request.y },
        { width: node.current.offsetWidth, height: node.current.offsetHeight },
        { width: window.innerWidth, height: window.innerHeight },
      ),
    );
    node.current.querySelector("button")?.focus({ preventScroll: true });
  }, [request]);

  useEffect(() => {
    if (!request) return;
    const away = (event: Event) => {
      if (!(event.target instanceof Node) || !node.current?.contains(event.target))
        onClose();
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    window.addEventListener("scroll", onClose, true);
    window.addEventListener("resize", onClose);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("scroll", onClose, true);
      window.removeEventListener("resize", onClose);
    };
  }, [request, onClose]);

  if (!request) return null;
  return (
    <div
      ref={node}
      className="lw-menu"
      role="menu"
      aria-label="Manuscript actions"
      style={place ? { left: place.left, top: place.top } : { visibility: "hidden" }}
    >
      {request.actions.map((action) => (
        <button
          key={action.label}
          type="button"
          role="menuitem"
          className="lw-menu-item"
          // Focus must not leave the prose on mousedown, or the words the
          // action is about are deselected before the click lands.
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => {
            onClose();
            action.run();
          }}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}
