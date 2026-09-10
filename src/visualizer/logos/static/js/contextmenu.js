// The manuscript's own right-click menu.
//
// It is only ever shown when the caller supplies at least one action, so the
// browser's native menu -- which carries paste and the spellchecker's
// suggestions -- survives everywhere else. That policy lives in the caller;
// this module renders, places and dismisses.

import { el as browserEl, fill as browserFill } from "./dom.js";

const EDGE = 8;

/** Where a menu of this size fits, given where the pointer was. */
export function menuPosition(pointer, menu, viewport) {
  return {
    left: Math.max(EDGE, Math.min(pointer.x, viewport.width - menu.width - EDGE)),
    top: Math.max(EDGE, Math.min(pointer.y, viewport.height - menu.height - EDGE)),
  };
}

export function createContextMenu({
  host, ui = { el: browserEl, fill: browserFill },
}) {
  const { el, fill } = ui;
  const node = el("div", {
    class: "writer-context-menu", role: "menu", hidden: true,
    "aria-label": "Manuscript actions",
  });
  host.appendChild(node);

  const close = () => {
    node.hidden = true;
    fill(node, []);
  };

  const item = ({ label, run }) => el("button", {
    class: "writer-menu-item", type: "button", role: "menuitem", text: label,
    // Focus must not leave the prose on mousedown, or the range the action is
    // about is already gone by the time the click lands.
    onmousedown: (event) => event.preventDefault(),
    onclick: () => { close(); run(); },
  });

  /** Show `actions` at the pointer. Returns false when there is nothing to show. */
  const open = (event, actions) => {
    if (!actions.length) return false;
    event.preventDefault();
    const buttons = actions.map(item);
    fill(node, buttons);
    node.hidden = false;
    const place = menuPosition(
      { x: event.clientX, y: event.clientY },
      { width: node.offsetWidth, height: node.offsetHeight },
      { width: window.innerWidth, height: window.innerHeight },
    );
    node.style.left = `${place.left}px`;
    node.style.top = `${place.top}px`;
    buttons[0].focus({ preventScroll: true });
    return true;
  };

  const holds = (target) => node.contains(target);
  const isOpen = () => !node.hidden;

  return { open, close, holds, isOpen };
}
