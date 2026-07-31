// History panel: list retained versions, compare any version with the current
// one (or an arbitrary pair), and restore an old version as a new revision.

import { el, clear, toast } from "./dom.js";
import { api } from "./api.js";
import { renderDiff } from "./diffview.js";

export async function renderHistory(container, { db, col, id }, handlers) {
  clear(container);
  container.hidden = false;
  container.appendChild(el("div", { class: "pane-toolbar" }, [
    el("span", { class: "crumbs", text: `History · ${db} › ${col} › ${id}` }),
    el("span", { class: "spacer" }),
    el("button", { class: "btn sm secondary", text: "Back to article", onclick: () => handlers.onBack() }),
  ]));

  let data;
  try { data = await api.listVersions(db, col, id); }
  catch (e) { container.appendChild(el("p", { class: "muted", text: "Could not load history." })); return; }

  const versions = data.versions; // newest first
  const current = versions.length ? versions[0].rev : null;
  const diffOut = el("div", { style: "margin-top:1.25rem" });

  const compare = async (from, to) => {
    clear(diffOut);
    diffOut.appendChild(el("p", { class: "muted", text: `Comparing revision ${from} → ${to}` }));
    try {
      const res = await api.diff(db, col, id, from, to);
      diffOut.appendChild(renderDiff(res.diff));
    } catch (e) { diffOut.appendChild(el("p", { class: "muted", text: "One of these versions is no longer retained." })); }
  };

  const list = el("div", { class: "history-list" });
  const retained = new Set(versions.map((v) => v.rev));
  for (const v of versions) {
    const isCurrent = v.rev === current;
    const canPrev = retained.has(v.rev - 1);
    const row = el("div", { class: "history-row" }, [
      el("div", { class: "hr-main" }, [
        el("span", { class: "hr-rev", text: `rev ${v.rev}` }),
        isCurrent ? el("span", { class: "hr-op", text: " current" }) : el("span", { class: "hr-op", text: " " + (v.op || "") }),
        el("div", { class: "hr-time", text: `${v.author || "—"} · ${fmt(v.timestamp)}` }),
      ]),
      !isCurrent ? el("button", { class: "btn sm secondary", text: "Compare with current", onclick: () => compare(v.rev, current) }) : null,
      !isCurrent && canPrev ? el("button", { class: "btn sm secondary", text: "Δ prev", title: "Compare with previous", onclick: () => compare(v.rev - 1, v.rev) }) : null,
      v.op !== "delete" ? el("button", { class: "btn sm", text: "Restore", onclick: () => doRestore(v.rev) }) : null,
    ]);
    list.appendChild(row);
  }

  async function doRestore(rev) {
    try { const r = await api.restore(db, col, id, rev); toast(`Restored revision ${rev} as revision ${r.rev}.`); handlers.onRestored(); }
    catch (e) { toast(e.message || "Restore failed.", true); }
  }

  container.appendChild(list);
  container.appendChild(diffOut);
}

function fmt(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch (e) { return iso; }
}
