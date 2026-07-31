// The edit-time link type-ahead. Triggered by typing "[[" or an "Insert link"
// button; searches /suggest, inserts the shortest unambiguous [[token|title]],
// and offers "Create new article" when nothing matches.

import { api } from "./api.js";
import { el, clear } from "./dom.js";
import { shortestToken } from "./links.js";

export function attachLinkPicker(textarea, scope, { onCreateRequest }) {
  let picker = null;
  let caret = 0;       // insertion point for the completed token
  let debounce = null;

  function close() {
    if (picker) { picker.remove(); picker = null; }
  }

  function insertAt(text, at) {
    const pos = at != null ? at : textarea.selectionStart;
    textarea.value = textarea.value.slice(0, pos) + text + textarea.value.slice(pos);
    const end = pos + text.length;
    textarea.setSelectionRange(end, end);
  }

  function chooseTarget(target) {
    const token = shortestToken(target, scope);
    const label = target.title && target.title !== target.id ? `|${target.title}` : "";
    close();
    insertAt(`[[${token}${label}]]`, caret);
    textarea.focus();
    textarea.dispatchEvent(new Event("input"));
  }

  async function renderResults(node, query) {
    clear(node);
    const q = query.trim();
    let items = [];
    if (q) { try { items = (await api.suggest(query, scope.db, scope.col)).suggestions; } catch (e) { /* ignore */ } }
    if (!picker) return; // closed while awaiting
    clear(node);
    for (const s of items) {
      node.appendChild(el("div", {
        class: "lp-item",
        onclick: () => chooseTarget({ db: s.database, col: s.collection, id: s.slug, title: s.title }),
      }, [
        el("div", { class: "lp-title", text: s.title || s.slug }),
        el("div", { class: "lp-scope", text: `${s.database} / ${s.collection} / ${s.slug}` }),
      ]));
    }
    if (q) {
      node.appendChild(el("div", {
        class: "lp-item lp-create",
        text: `Create “${q}”…`,
        onclick: async () => { const t = await onCreateRequest(q, scope); if (t) chooseTarget(t); },
      }));
    } else if (!items.length) {
      node.appendChild(el("div", { class: "lp-item muted", text: "Type to search articles…" }));
    }
  }

  function open(initialQuery = "") {
    close();
    caret = textarea.selectionStart;
    const rect = textarea.getBoundingClientRect();
    const input = el("input", { type: "search", placeholder: "Link to article…", value: initialQuery });
    const results = el("div", { class: "lp-results" });
    picker = el("div", { class: "link-picker" }, [el("div", { style: "padding:.5rem" }, [input]), results]);
    document.body.appendChild(picker);
    picker.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - 340))}px`;
    picker.style.top = `${rect.bottom + window.scrollY + 4}px`;
    input.addEventListener("input", () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => renderResults(results, input.value), 160);
    });
    input.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    renderResults(results, initialQuery);
    setTimeout(() => input.focus(), 0);
  }

  // "[[" trigger: drop the brackets and open the picker.
  textarea.addEventListener("input", () => {
    const pos = textarea.selectionStart;
    if (textarea.value.slice(pos - 2, pos) === "[[") {
      textarea.value = textarea.value.slice(0, pos - 2) + textarea.value.slice(pos);
      textarea.setSelectionRange(pos - 2, pos - 2);
      open("");
    }
  });

  document.addEventListener("click", (e) => {
    if (picker && !picker.contains(e.target) && e.target !== textarea) close();
  });

  return { open };
}
