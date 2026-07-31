// Edit view: title + wikitext body (with toolbar, link picker, live preview) +
// infobox facts, plus a hidden Advanced raw-JSON mode. Saves through the store's
// OCC path and resolves 409 conflicts with a diff.

import { el, clear, toast, modal } from "./dom.js";
import { api, ApiError } from "./api.js";
import { splitArticle, assembleArticle, parseFactValue, factValueToInput } from "./article.js";
import { renderWikitext } from "./wikitext.js";
import { attachLinkPicker } from "./linkpicker.js";
import { localDiff, renderDiff } from "./diffview.js";

export function renderEditor(container, ctx, handlers) {
  const { db, col, id, doc, rev, isNew } = ctx;
  const article = splitArticle(doc || {}, id);
  clear(container);
  container.hidden = false;

  const titleInput = el("input", { type: "text", class: "edit-title", value: article.hasTitle ? article.title : (isNew ? "" : article.title), placeholder: "Article title" });
  const bodyArea = el("textarea", { class: "body-textarea", text: article.body, placeholder: "Write with wikitext — '''bold''', == Heading ==, * list, [[link]]" });
  const preview = el("div", { class: "preview-pane" }, [el("div", { class: "preview-label", text: "Preview" }), el("div", { class: "article-body" })]);
  const split = el("div", { class: "editor-split" }, [bodyArea]);

  const picker = attachLinkPicker(bodyArea, { db, col }, { onCreateRequest: handlers.onCreateLink });

  const toolbar = el("div", { class: "edit-toolbar" }, [
    _tbBtn("Bold", () => wrap(bodyArea, "'''", "'''")),
    _tbBtn("Italic", () => wrap(bodyArea, "''", "''")),
    _tbBtn("Heading", () => linePrefix(bodyArea, "== ", " ==")),
    _tbBtn("List", () => linePrefix(bodyArea, "* ", "")),
    _tbBtn("🔗 Insert link", () => picker.open("")),
    _tbBtn("👁 Preview", () => togglePreview()),
  ]);

  function refreshPreview() {
    preview.querySelector(".article-body").innerHTML = renderWikitext(bodyArea.value);
  }
  let previewOn = false;
  function togglePreview() {
    previewOn = !previewOn;
    split.classList.toggle("preview-on", previewOn);
    if (previewOn) { split.appendChild(preview); refreshPreview(); }
    else preview.remove();
  }
  bodyArea.addEventListener("input", () => { if (previewOn) refreshPreview(); });

  // infobox facts editor
  const factsWrap = el("div", {});
  const factRows = [];
  const addFact = (key = "", value = "") => {
    const keyIn = el("input", { type: "text", class: "fact-key", value: key, placeholder: "field" });
    const valIn = el("input", { type: "text", value, placeholder: "value (comma-separates into a list)" });
    const row = el("div", { class: "fact-row" }, [keyIn, valIn,
      el("button", { class: "btn sm danger", text: "✕", onclick: () => { row.remove(); const i = factRows.indexOf(rec); if (i >= 0) factRows.splice(i, 1); } })]);
    const rec = { keyIn, valIn };
    factRows.push(rec);
    factsWrap.appendChild(row);
  };
  article.facts.forEach((f) => addFact(f.key, factValueToInput(f.value)));

  const infoboxEditor = el("div", { class: "infobox-editor" }, [
    el("h3", { text: "Article details (infobox)" }),
    factsWrap,
    el("button", { class: "btn sm secondary", text: "＋ Add a fact", onclick: () => addFact() }),
  ]);

  // advanced raw JSON
  const rawArea = el("textarea", {});
  const rawWrap = el("div", { class: "raw-editor", hidden: "hidden" }, [
    el("label", { text: "Raw document (flat JSON)" }), rawArea,
  ]);
  let advancedOn = false;
  const advancedToggle = el("button", { class: "advanced-toggle", text: "▸ Advanced (raw fields)", onclick: () => toggleAdvanced() });
  function collectArticle() {
    return assembleArticle({
      title: titleInput.value,
      body: bodyArea.value,
      facts: factRows.map((r) => ({ key: r.keyIn.value, value: parseFactValue(r.valIn.value) })),
    });
  }
  function toggleAdvanced() {
    advancedOn = !advancedOn;
    advancedToggle.textContent = (advancedOn ? "▾" : "▸") + " Advanced (raw fields)";
    rawWrap.hidden = !advancedOn;
    if (advancedOn) rawArea.value = JSON.stringify(collectArticle(), null, 2);
  }

  const saveBtn = el("button", { class: "btn", text: isNew ? "Create" : "Save" });
  const status = el("span", { class: "muted" });
  saveBtn.addEventListener("click", () => save());

  async function save() {
    let document;
    if (advancedOn) {
      try { document = JSON.parse(rawArea.value); }
      catch (e) { toast("Raw JSON is invalid.", true); return; }
    } else {
      document = collectArticle();
    }
    saveBtn.disabled = true; status.textContent = "Saving…";
    try {
      const result = isNew
        ? await api.createDoc(db, col, id, document)
        : await api.updateDoc(db, col, id, document, rev);
      toast(isNew ? "Article created." : "Saved.");
      handlers.onSaved(result.rev);
    } catch (e) {
      saveBtn.disabled = false; status.textContent = "";
      if (e instanceof ApiError && e.isConflict) return resolveConflict(document);
      toast(e.message || "Save failed.", true);
    }
  }

  async function resolveConflict(myDoc) {
    let current;
    try { current = await api.getDoc(db, col, id); }
    catch (e) { toast("Conflict, and the article could not be reloaded.", true); return; }
    const diff = localDiff(current.document, myDoc);
    modal({
      title: "This article changed while you were editing",
      body: el("div", {}, [
        el("p", { class: "muted", text: `It is now at revision ${current.rev}. Your changes vs the current version:` }),
        renderDiff(diff),
      ]),
      actions: [
        { label: "Reload theirs", variant: "secondary", onClick: (close) => { close(); handlers.onReload(); } },
        { label: "Keep mine (overwrite)", variant: "danger", onClick: async (close) => {
            try { const r = await api.updateDoc(db, col, id, myDoc, current.rev); toast("Saved over the newer version."); close(); handlers.onSaved(r.rev); }
            catch (err) { toast(err.message || "Overwrite failed.", true); }
          } },
      ],
    });
  }

  container.appendChild(el("div", { class: "pane-toolbar" }, [
    el("span", { class: "crumbs", text: `${db} › ${col} › ${id}` }),
    el("span", { class: "spacer" }),
    saveBtn, status,
    el("button", { class: "btn sm secondary", text: "Cancel", onclick: () => handlers.onCancel() }),
  ]));
  container.appendChild(el("label", { text: "Title" }));
  container.appendChild(titleInput);
  container.appendChild(toolbar);
  container.appendChild(split);
  container.appendChild(infoboxEditor);
  container.appendChild(el("div", { style: "margin-top:1rem" }, [advancedToggle, rawWrap]));
}

function _tbBtn(label, onClick) { return el("button", { type: "button", text: label, onclick: onClick }); }

function wrap(area, pre, post) {
  const s = area.selectionStart, e = area.selectionEnd;
  const sel = area.value.slice(s, e) || "text";
  area.value = area.value.slice(0, s) + pre + sel + post + area.value.slice(e);
  area.focus();
  area.setSelectionRange(s + pre.length, s + pre.length + sel.length);
  area.dispatchEvent(new Event("input"));
}

function linePrefix(area, pre, post) {
  const s = area.selectionStart;
  const lineStart = area.value.lastIndexOf("\n", s - 1) + 1;
  const lineEnd = area.value.indexOf("\n", s);
  const end = lineEnd === -1 ? area.value.length : lineEnd;
  const line = area.value.slice(lineStart, end);
  area.value = area.value.slice(0, lineStart) + pre + line + post + area.value.slice(end);
  area.focus();
  area.dispatchEvent(new Event("input"));
}
