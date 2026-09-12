// Dragging the contents organiser with a finger.
//
// HTML5 drag-and-drop never raises an event from touch -- no polyfill-free
// trick changes that -- so without this the ⠿ handles are inert on a phone or
// tablet and the arrow and Move… controls are the only way to rearrange a book.
// Pointer events cover touch, pen and mouse alike, but the mouse already has a
// working native drag, so this engages only for the pointer types that need it
// and leaves the desktop path exactly as it was.
//
// The gesture is long-press-then-drag, the convention on both mobile platforms.
// Engaging on contact would turn every stray touch of a 44px control into a
// reorder, and would make the handle impossible to scroll past.
//
// Geometry lives in `contents.js` as pure functions; what is here is the part
// that needs a pointer, a clock and a viewport.

import { dropAt, volumeDropAt } from "./contents.js";

const HOLD_MS = 200; // press this long before a drag engages
const SLOP_PX = 8; // movement before that cancels it as a scroll
const EDGE_PX = 72; // how near an edge auto-scrolling starts
const EDGE_STEP = 12; // pixels per frame while scrolling

/**
 * @param zones     reads the current geometry: volumes, each with its rows.
 * @param onSection called with (payload, volumeId, before) for a chapter drop.
 * @param onVolume  called with (payload, before) for a volume drop.
 * @param view      the window seam, injected so the gesture can be driven in a
 *                  test without a browser.
 */
export function createTouchDrag({ zones, onSection, onVolume, view = window }) {
  let press = null;
  let drag = null;
  let frame = null;
  let pointerY = 0;

  function begin(event, payload) {
    if (event.pointerType === "mouse") return;
    const node = event.currentTarget;
    press = { payload, node, pointerId: event.pointerId };
    press.from = { x: event.clientX, y: event.clientY };
    press.timer = view.setTimeout(engage, HOLD_MS);
    node.addEventListener("pointermove", onMove);
    node.addEventListener("pointerup", onUp);
    node.addEventListener("pointercancel", onCancel);
  }

  function engage() {
    if (!press) return;
    drag = { payload: press.payload, node: press.node };
    press.timer = null;
    try {
      press.node.setPointerCapture(press.pointerId);
    } catch {
      // A pointer the browser has already taken back cannot be captured; the
      // press simply never becomes a drag.
      drag = null;
      return;
    }
    holder(press.node)?.classList.add("dragging");
    view.navigator?.vibrate?.(10);
  }

  function onMove(event) {
    pointerY = event.clientY;
    if (!drag) {
      const moved = Math.abs(event.clientX - press.from.x)
        + Math.abs(event.clientY - press.from.y);
      if (moved > SLOP_PX) release();
      return;
    }
    event.preventDefault();
    paint(event.clientY);
    scrollAtEdges();
  }

  function onUp(event) {
    const held = drag;
    const y = event.clientY;
    release();
    if (!held) return;
    const geometry = zones();
    if (held.payload.type === "volume") {
      const drop = volumeDropAt(geometry, y, held.payload.id);
      if (drop) onVolume(held.payload, drop.before);
      return;
    }
    const drop = dropAt(geometry, y);
    if (drop) onSection(held.payload, drop.volume, drop.before);
  }

  function onCancel() {
    release();
  }

  /**
   * Show where it would land: a line above the row it goes in front of, or
   * along the bottom of the volume it would be appended to.
   */
  function paint(y) {
    clearCues();
    const geometry = zones();
    if (drag.payload.type === "volume") {
      const drop = volumeDropAt(geometry, y, drag.payload.id);
      if (!drop) return;
      if (drop.before) cue(card(drop.before), "drop-target");
      else cue(card(geometry[geometry.length - 1]?.volume), "drop-target-end");
      return;
    }
    const drop = dropAt(geometry, y);
    if (!drop) return;
    if (drop.before) cue(row(drop.volume, drop.before), "drop-target");
    else cue(card(drop.volume), "drop-target-end");
  }

  function card(volume) {
    if (!volume) return null;
    return view.document.querySelector(
      `.volume-card[data-volume="${CSS.escape(volume)}"]`,
    );
  }

  function row(volume, section) {
    return view.document.querySelector(
      `.section-row[data-volume="${CSS.escape(volume)}"]`
      + `[data-section="${CSS.escape(section)}"]`,
    );
  }

  function cue(node, className) {
    node?.classList.add(className);
  }

  function clearCues() {
    view.document.querySelectorAll(".drop-target, .drop-target-end").forEach(
      (node) => node.classList.remove("drop-target", "drop-target-end"),
    );
  }

  /** A phone shows four rows; without this a chapter cannot reach volume two. */
  function scrollAtEdges() {
    if (frame !== null) return;
    const step = () => {
      if (!drag) {
        frame = null;
        return;
      }
      if (pointerY < EDGE_PX) view.scrollBy(0, -EDGE_STEP);
      else if (pointerY > view.innerHeight - EDGE_PX) view.scrollBy(0, EDGE_STEP);
      frame = view.requestAnimationFrame(step);
    };
    frame = view.requestAnimationFrame(step);
  }

  function holder(node) {
    return node.closest(".section-row, .volume-card");
  }

  function release() {
    if (press) {
      if (press.timer !== null) view.clearTimeout(press.timer);
      press.node.removeEventListener("pointermove", onMove);
      press.node.removeEventListener("pointerup", onUp);
      press.node.removeEventListener("pointercancel", onCancel);
      try {
        press.node.releasePointerCapture(press.pointerId);
      } catch {
        // Already released, which is the ordinary case on pointerup.
      }
      holder(press.node)?.classList.remove("dragging");
    }
    if (frame !== null) {
      view.cancelAnimationFrame(frame);
      frame = null;
    }
    clearCues();
    press = null;
    drag = null;
  }

  return { begin, release };
}
