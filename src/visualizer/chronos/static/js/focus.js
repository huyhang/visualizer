// Focus mode: hide the continuity marks so a thread can be arranged in peace.
//
// Two rules shape it. **It hides, it never silences** — nothing stops being
// computed, the preview still runs, and a save behaves identically; only the
// marks are out of sight. And **the button always says what it is hiding**
// ("Show 2 problems"), so a writer who leaves it on cannot mistake a quiet
// screen for a sound story. Everything is done with one class on <body>, so
// toggling is instant and costs no re-render and no request.
//
// Deliberately scoped to the plotline view and the editor — the places where a
// writer is arranging scenes. The book's table keeps its health column, because
// a table that looked clean while hiding problems would simply be wrong.

import { el } from "./dom.js";

const KEY = "chronos-focus";
const CLASS = "focus-mode";

export function focusHidden() {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch (e) {
    return false; // private browsing, blocked storage — just show the marks
  }
}

export function applyFocus() {
  document.body.classList.toggle(CLASS, focusHidden());
}

function setFocus(hidden) {
  try {
    localStorage.setItem(KEY, hidden ? "1" : "0");
  } catch (e) { /* the class below still applies for this page */ }
  document.body.classList.toggle(CLASS, hidden);
}

function label(hidden, conflicts) {
  if (!hidden) return "Hide problems";
  if (conflicts) return `Show ${conflicts} problem${conflicts === 1 ? "" : "s"}`;
  return "Show notes";
}

// A button that flips the mode. `conflicts` is the thread's problem count, used
// only for the label. `onToggle` lets a caller relabel its own chrome.
export function focusToggle(conflicts, { onToggle } = {}) {
  const button = el("button", {
    class: "btn secondary sm focus-btn",
    type: "button",
    text: label(focusHidden(), conflicts),
    title: "Continuity marks stay computed either way — this only hides them.",
  });
  button.addEventListener("click", () => {
    const hidden = !focusHidden();
    setFocus(hidden);
    button.textContent = label(hidden, conflicts);
    if (onToggle) onToggle(hidden);
  });
  return button;
}
