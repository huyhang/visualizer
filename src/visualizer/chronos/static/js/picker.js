// Two small, reusable interaction pieces the editor is built from: a modal
// panel, and a type-ahead field that searches something and hands back what was
// chosen. Neither knows what it is choosing — the caller supplies the search
// function and the row renderer — so the scene picker, the article picker and
// the "continues into" picker are all the same component.

import { clear, el } from "./dom.js";

const DEBOUNCE_MS = 200;

// A modal over the page. Returns { close }; Esc and the backdrop both dismiss.
export function modal(title, body, { onClose, wide = false } = {}) {
  const close = () => {
    document.removeEventListener("keydown", onKey);
    overlay.remove();
    if (onClose) onClose();
  };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };

  const panel = el("div", { class: `modal-panel${wide ? " wide" : ""}`, role: "dialog", "aria-modal": "true" }, [
    el("div", { class: "modal-head" }, [
      el("span", { class: "modal-title", text: title }),
      el("button", { class: "icon-btn sm", type: "button", text: "✕", title: "Close", onclick: close }),
    ]),
    el("div", { class: "modal-body" }, body),
  ]);
  const overlay = el("div", {
    class: "modal-overlay",
    onclick: (e) => { if (e.target === overlay) close(); },
  }, panel);

  document.addEventListener("keydown", onKey);
  document.body.appendChild(overlay);
  const firstInput = panel.querySelector("input");
  if (firstInput) firstInput.focus();
  return { close, panel };
}

// A yes/no modal. `body` may be any node (the delete dialog uses it to list the
// threads that would be affected). Resolves nothing — the caller acts in onYes.
export function confirmModal(title, body, { yes = "Confirm", danger = false, onYes }) {
  const buttons = el("div", { class: "form-actions" });
  const dialog = modal(title, el("div", {}, [
    typeof body === "string" ? el("p", { text: body }) : body,
    buttons,
  ]));
  buttons.appendChild(el("button", {
    class: danger ? "btn danger" : "btn", type: "button", text: yes,
    onclick: () => { dialog.close(); onYes(); },
  }));
  buttons.appendChild(el("button", {
    class: "btn secondary", type: "button", text: "Cancel", onclick: dialog.close,
  }));
  return dialog;
}

// A search box with its results underneath.
//   search(query) -> Promise<item[]>      renderItem(item) -> Node
//   onPick(item)                          empty: what to say when nothing matches
// Results refresh as the writer types (debounced, and out-of-order responses are
// discarded so a slow early query cannot overwrite a fast later one).
export function suggestBox({ placeholder, search, renderItem, onPick, empty = "Nothing found.", autoSearch = true }) {
  const results = el("div", { class: "suggest-results" });
  const input = el("input", { type: "search", placeholder, autocomplete: "off" });
  let timer = null;
  let seq = 0;

  async function run() {
    const mine = ++seq;
    const query = input.value.trim();
    try {
      const items = await search(query);
      if (mine !== seq) return; // a later keystroke already answered
      clear(results);
      if (!items.length) {
        results.appendChild(el("p", { class: "muted suggest-empty", text: empty }));
        return;
      }
      for (const item of items) {
        results.appendChild(el("button", {
          class: "suggest-row", type: "button", onclick: () => onPick(item),
        }, renderItem(item)));
      }
    } catch (e) {
      if (mine !== seq) return;
      clear(results);
      results.appendChild(el("p", { class: "muted suggest-empty", text: "Could not search." }));
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(run, DEBOUNCE_MS);
  });
  input.addEventListener("keydown", (e) => {
    // Enter takes the first match — the common case when you know the name.
    if (e.key !== "Enter") return;
    e.preventDefault();
    const first = results.querySelector(".suggest-row");
    if (first) first.click();
  });

  if (autoSearch) run();
  return { el: el("div", { class: "suggest" }, [input, results]), input, refresh: run };
}
