// Tiny DOM helpers shared across modules. Everything builds via textContent /
// createElement (never innerHTML with untrusted data) except the wikitext
// renderer, which does its own escaping.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v; // caller guarantees safety
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

export function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

let toastTimer = null;
export function toast(message, isError = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = "toast" + (isError ? " err" : "");
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 3200);
}

// A modal over the page. Escape, the ✕ and the backdrop all dismiss it, and the
// first field takes focus so a dialog can be filled in without reaching for the
// mouse. Returns `close` so a caller's action can dismiss it once its work is
// done. `onClose` fires however it was dismissed — a caller waiting on an answer
// needs to hear about a cancel too.
export function modal({ title, body, actions, onClose }) {
  const close = () => {
    document.removeEventListener("keydown", onKey);
    scrim.remove();
    if (onClose) onClose();
  };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };

  const foot = el("div", { class: "modal-foot" },
    (actions || []).map((a) =>
      el("button", {
        class: "btn " + (a.variant || "secondary"),
        type: "button",
        text: a.label,
        onclick: () => a.onClick ? a.onClick(close) : close(),
      })));
  const dialog = el("div", { class: "modal", role: "dialog", "aria-modal": "true" }, [
    el("div", { class: "modal-head" }, [
      el("span", { class: "modal-title", text: title }),
      el("button", { class: "icon-btn sm", type: "button", text: "✕", title: "Close", onclick: () => close() }),
    ]),
    el("div", { class: "modal-body" }, [body]),
    foot,
  ]);
  const scrim = el("div", {
    class: "modal-scrim",
    onclick: (e) => { if (e.target === scrim) close(); },
  }, [dialog]);

  document.addEventListener("keydown", onKey);
  document.body.appendChild(scrim);
  const first = dialog.querySelector("input, select, textarea");
  if (first) first.focus();
  return close;
}
