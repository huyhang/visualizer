// Main orchestrator: wires the browser, viewer, editor and history together,
// with hash-based routing (#/db/col/id) so links and reloads are shareable.

import { $, el, clear, toast, modal } from "./dom.js";
import { api, ApiError } from "./api.js";
import { initTheme } from "./theme.js";
import { initFontScale } from "./fontscale.js";
import { Browser } from "./browser.js";
import { renderArticle } from "./viewer.js";
import { renderEditor } from "./editor.js";
import { renderHistory } from "./history.js";
import { invalidate } from "./links.js";

const pane = $("#pane");
const emptyState = $("#empty-state");
const sidebar = $("#sidebar");

const browser = new Browser($("#tree"), { onOpen: (t) => navigate(t) });

function showPane() { emptyState.hidden = true; pane.hidden = false; }
function showEmpty() { pane.hidden = true; emptyState.hidden = false; }
function closeDrawer() { sidebar.classList.remove("open"); $("#scrim").hidden = true; }

function keyOf(t) { return `${t.db}/${t.col}/${t.id}`; }
function navigate(target) { location.hash = `#/${enc(target.db)}/${enc(target.col)}/${enc(target.id)}`; }
const enc = encodeURIComponent;

function parseHash() {
  const m = location.hash.match(/^#\/([^/]+)\/([^/]+)\/([^/]+)$/);
  if (!m) return null;
  return { db: decodeURIComponent(m[1]), col: decodeURIComponent(m[2]), id: decodeURIComponent(m[3]) };
}

async function openFromHash() {
  const target = parseHash();
  if (!target) { showEmpty(); return; }
  closeDrawer();
  browser.setActive(keyOf(target));
  await openArticle(target);
}

async function openArticle(target) {
  showPane();
  clear(pane);
  pane.appendChild(el("p", { class: "muted", text: "Loading…" }));
  let doc;
  try { doc = await api.getDoc(target.db, target.col, target.id); }
  catch (e) { return renderError(e, target); }
  await renderArticle(pane, { ...target, doc: doc.document, rev: doc.rev }, {
    onNavigate: (t) => navigate(t),
    onEdit: () => openEditor({ ...target, doc: doc.document, rev: doc.rev, isNew: false }),
    onHistory: () => openHistory(target),
    onDelete: (rev) => confirmDelete(target, rev),
  });
}

function renderError(e, target) {
  clear(pane);
  const msg = e instanceof ApiError && e.isForbidden ? "You do not have access to this article."
    : e instanceof ApiError && e.isNotFound ? "This article does not exist."
    : "Could not load this article.";
  pane.appendChild(el("div", { class: "pane-toolbar" }, [el("span", { class: "crumbs", text: `${target.db} › ${target.col} › ${target.id}` })]));
  pane.appendChild(el("p", { class: "muted", text: msg }));
  if (e instanceof ApiError && e.isNotFound) {
    pane.appendChild(el("button", { class: "btn", text: "Create this article", onclick: () => openEditor({ ...target, doc: {}, rev: null, isNew: true }) }));
  }
}

function openEditor(ctx) {
  showPane();
  renderEditor(pane, ctx, {
    onSaved: (rev) => { invalidate(ctx); browser.load(); navigate(ctx); if (parseHash() && keyOf(parseHash()) === keyOf(ctx)) openFromHash(); },
    onCancel: () => ctx.isNew ? showEmpty() : openArticle(ctx),
    onReload: () => openArticle(ctx),
    onCreateLink: (query, scope) => createLinkTarget(query, scope),
  });
}

function openHistory(target) {
  showPane();
  renderHistory(pane, target, {
    onBack: () => openArticle(target),
    onRestored: () => { invalidate(target); openArticle(target); },
  });
}

function confirmDelete(target, rev) {
  modal({
    title: "Delete this article?",
    body: el("p", { text: `“${target.id}” will be removed. Its version history is kept, and it can be recreated later.` }),
    actions: [
      { label: "Cancel", variant: "secondary" },
      { label: "Delete", variant: "danger", onClick: async (close) => {
          try { await api.deleteDoc(target.db, target.col, target.id, rev); toast("Article deleted."); close(); invalidate(target); browser.load(); location.hash = ""; showEmpty(); }
          catch (e) { toast(e.message || "Delete failed.", true); }
        } },
    ],
  });
}

// -- create flows ----------------------------------------------------------

function slugify(text) {
  return text.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "untitled";
}

// Create-on-the-fly from the link picker: make a stub article, return its target.
function createLinkTarget(query, scope) {
  return new Promise((resolve) => {
    const slug = el("input", { type: "text", value: slugify(query) });
    const colIn = el("input", { type: "text", value: scope.col });
    const close = modal({
      title: `Create “${query}”`,
      body: el("div", {}, [
        el("div", { class: "field" }, [el("label", { text: "Collection" }), colIn]),
        el("div", { class: "field" }, [el("label", { text: "Slug (id)" }), slug]),
      ]),
      actions: [
        { label: "Cancel", variant: "secondary", onClick: (c) => { c(); resolve(null); } },
        { label: "Create", variant: "primary", onClick: async (c) => {
            const target = { db: scope.db, col: colIn.value.trim(), id: slug.value.trim(), title: query };
            try {
              await ensureCollection(target.db, target.col);
              await api.createDoc(target.db, target.col, target.id, { title: query });
              toast(`Created “${query}”.`); c(); browser.load(); resolve(target);
            } catch (e) { toast(e.message || "Could not create.", true); }
          } },
      ],
    });
  });
}

async function ensureCollection(db, col) {
  try { await api.createCollection(db, col); }
  catch (e) { if (!(e instanceof ApiError && e.status === 409)) throw e; }
}

function newArticleFlow() {
  const dbIn = el("input", { type: "text", placeholder: "database" });
  const colIn = el("input", { type: "text", placeholder: "collection" });
  const titleIn = el("input", { type: "text", placeholder: "Article title" });
  const slugIn = el("input", { type: "text", placeholder: "slug (id)" });
  titleIn.addEventListener("input", () => { if (!slugIn._touched) slugIn.value = slugify(titleIn.value); });
  slugIn.addEventListener("input", () => { slugIn._touched = true; });
  modal({
    title: "New article",
    body: el("div", {}, [
      el("div", { class: "field" }, [el("label", { text: "Database" }), dbIn]),
      el("div", { class: "field" }, [el("label", { text: "Collection" }), colIn]),
      el("div", { class: "field" }, [el("label", { text: "Title" }), titleIn]),
      el("div", { class: "field" }, [el("label", { text: "Slug (id)" }), slugIn]),
    ]),
    actions: [
      { label: "Cancel", variant: "secondary" },
      { label: "Continue", variant: "primary", onClick: async (close) => {
          const db = dbIn.value.trim(), col = colIn.value.trim(), id = slugIn.value.trim();
          if (!db || !col || !id) { toast("Database, collection and slug are required.", true); return; }
          try { await ensureCollection(db, col); }
          catch (e) { toast(e.message || "Could not create the collection.", true); return; }
          close();
          openEditor({ db, col, id, doc: titleIn.value ? { title: titleIn.value.trim() } : {}, rev: null, isNew: true });
        } },
    ],
  });
}

// -- search (link-style type-ahead in the sidebar) -------------------------

let searchTimer = null;
function initSearch() {
  const box = $("#search-box");
  box.addEventListener("input", () => {
    clearTimeout(searchTimer);
    const q = box.value.trim();
    if (!q) { browser.load(); return; }
    searchTimer = setTimeout(async () => {
      let res;
      try { res = await api.suggest(q); } catch (e) { return; }
      const tree = $("#tree"); clear(tree);
      if (!res.suggestions.length) { tree.appendChild(el("div", { class: "tree-empty", text: "No matches." })); return; }
      for (const s of res.suggestions) {
        tree.appendChild(el("div", { class: "tree-node" }, [
          el("div", { class: "tree-row", onclick: () => navigate({ db: s.database, col: s.collection, id: s.slug }) }, [
            el("span", { class: "twisty", text: "·" }),
            el("span", { text: s.title || s.slug }),
          ]),
        ]));
      }
    }, 200);
  });
}

// -- boot ------------------------------------------------------------------

function initChrome() {
  initTheme($("#theme-toggle"));
  initFontScale($("#font-toggle"));
  $("#menu-toggle").addEventListener("click", () => {
    const open = sidebar.classList.toggle("open");
    $("#scrim").hidden = !open;
  });
  $("#scrim").addEventListener("click", closeDrawer);
  $("#new-article-btn").addEventListener("click", newArticleFlow);
  initSearch();
}

initChrome();
browser.load();
window.addEventListener("hashchange", openFromHash);
openFromHash();
