// Renders a structured diff (from the server's /diff endpoint, or built locally
// for conflict resolution) as an intuitive field-by-field view.

import { el, escapeHtml } from "./dom.js";
import { factValueToInput } from "./article.js";

// Build the same {fields:[...]} structure the server returns, for two local
// document bodies (used in conflict resolution before we have a server diff).
export function localDiff(oldDoc, newDoc) {
  const keys = Array.from(new Set([...Object.keys(oldDoc || {}), ...Object.keys(newDoc || {})])).sort();
  const fields = keys.map((key) => {
    const inOld = oldDoc && key in oldDoc, inNew = newDoc && key in newDoc;
    if (inOld && !inNew) return { key, status: "removed", old: oldDoc[key] };
    if (inNew && !inOld) return { key, status: "added", new: newDoc[key] };
    if (JSON.stringify(oldDoc[key]) === JSON.stringify(newDoc[key]))
      return { key, status: "unchanged", old: oldDoc[key], new: newDoc[key] };
    return { key, status: "changed", old: oldDoc[key], new: newDoc[key] };
  });
  return { fields };
}

function inlineHtml(segments) {
  return segments.map((s) => {
    const t = escapeHtml(s.text);
    if (s.op === "insert") return `<ins class="d">${t}</ins>`;
    if (s.op === "delete") return `<del class="d">${t}</del>`;
    return t;
  }).join("");
}

function valueText(v) { return v == null ? "∅" : factValueToInput(v); }

export function renderDiff(diff, { includeUnchanged = false } = {}) {
  const wrap = el("div", { class: "diff" });
  for (const f of diff.fields) {
    if (f.status === "unchanged" && !includeUnchanged) continue;
    const body = el("div", { class: "df-body" });
    if (f.status === "added") {
      body.appendChild(el("div", { class: "df-new", text: "+ " + valueText(f.new) }));
    } else if (f.status === "removed") {
      body.appendChild(el("div", { class: "df-old", text: "− " + valueText(f.old) }));
    } else if (f.status === "changed" && f.inline) {
      body.appendChild(el("div", { html: inlineHtml(f.inline) }));
    } else if (f.status === "changed") {
      body.appendChild(el("div", { class: "df-old", text: "− " + valueText(f.old) }));
      body.appendChild(el("div", { class: "df-new", text: "+ " + valueText(f.new) }));
    } else {
      body.appendChild(el("div", { class: "muted", text: valueText(f.new) }));
    }
    wrap.appendChild(el("div", { class: "diff-field" }, [
      el("div", { class: "df-key" }, [
        el("span", { class: "df-tag " + f.status, text: f.status }),
        el("span", { text: f.key }),
      ]),
      body,
    ]));
  }
  if (!wrap.children.length) wrap.appendChild(el("p", { class: "muted", text: "No differences." }));
  return wrap;
}
