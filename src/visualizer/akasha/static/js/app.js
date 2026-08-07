// Main orchestrator: a hash router over four levels of the hierarchy, wiring
// the browse views, the tree, the viewer, the editor and the history together.
//
//   #/                  -> pick a world
//   #/<db>              -> pick a category
//   #/<db>/<col>        -> that category's filtered, paginated article list
//   #/<db>/<col>/<id>   -> one article
//   #/_search           -> search a category in detail
//
// Every level having a route is what makes the rest possible: a page to browse,
// and somewhere for a "New …" button to live that already knows where it is.
// (`_search` cannot collide with a real world — the API reserves every name
// beginning with an underscore.)
//
// Creating and sharing are modals rather than routes: they are detours from
// reading, and closing one should put you back exactly where you were.

import { $, el, clear, toast, modal } from "./dom.js";
import { api, ApiError } from "./api.js";
import { initTheme } from "./theme.js";
import { initFontScale } from "./fontscale.js";
import { Browser } from "./browser.js";
import { renderArticle } from "./viewer.js";
import { renderEditor } from "./editor.js";
import { renderHistory } from "./history.js";
import { invalidate } from "./links.js";
import { mountCollections, mountDatabases } from "./namespaces.js";
import { mountArticles } from "./articles.js";
import { mountSearch } from "./search.js";
import { timeAgo } from "./views.js";
import { T } from "./terms.js";
import {
  confirmDeleteDatabase, createLinkTarget, ensureCollection, newArticleDialog,
  newCollectionDialog, newDatabaseDialog,
} from "./create.js";

const SEARCH_ROUTE = "_search";

const pane = $("#pane");
const sidebar = $("#sidebar");

// Where the reader currently is, so a "New article" pressed from the header
// arrives with the world and category already filled in.
let scope = {};

// -- navigation --------------------------------------------------------------

const enc = encodeURIComponent;
const go = (hash) => { location.hash = hash; };
const toHome = () => go("#/");
const toDatabase = (db) => go(`#/${enc(db)}`);
const toCollection = (db, col) => go(`#/${enc(db)}/${enc(col)}`);
const toArticle = (t) => go(`#/${enc(t.db)}/${enc(t.col)}/${enc(t.id)}`);
const toSearch = () => go(`#/${SEARCH_ROUTE}`);

function parseHash() {
  return location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
}

function closeDrawer() {
  sidebar.classList.remove("open");
  $("#scrim").hidden = true;
}

// -- routing -----------------------------------------------------------------

const browseHandlers = {
  onHome: toHome,
  onDatabase: toDatabase,
  onCollection: toCollection,
  onArticle: (t) => toArticle(t),
  onCreate: (db, col) => (db ? newArticle({ db, col }) : newDatabase()),
  onDeleteDatabase: (db) => confirmDeleteDatabase(db, {
    onDeleted: () => { browser.load(); toHome(); },
  }),
  // A restored article is back in every listing, so the tree has to be told.
  onRestored: (db, col) => { invalidate({ db, col }); browser.refresh(db, col); },
};

async function route() {
  closeDrawer();
  const parts = parseHash();

  if (parts[0] === SEARCH_ROUTE) {
    browser.setActive("");
    // Keep the scope we arrived with, so the form opens on the collection you
    // were just reading rather than making you choose it again.
    return mountSearch(pane, scope, browseHandlers);
  }
  scope = { db: parts[0], col: parts[1], id: parts[2] };

  if (parts.length === 0) {
    browser.setActive("");
    return mountDatabases(pane, { ...browseHandlers, onCreate: newDatabase });
  }
  if (parts.length === 1) {
    browser.setActive("");
    return mountCollections(pane, parts[0], { ...browseHandlers, onCreate: newCollection });
  }
  if (parts.length === 2) {
    browser.setActive("");
    return mountArticles(pane, parts[0], parts[1], browseHandlers);
  }
  const target = { db: parts[0], col: parts[1], id: parts[2] };
  browser.reveal(target);
  await openArticle(target);
}

const browser = new Browser($("#tree"), {
  onArticle: (t) => toArticle(t),
  onDatabase: toDatabase,
  onCollection: toCollection,
});

// -- reading an article ------------------------------------------------------

async function openArticle(target) {
  clear(pane);
  pane.appendChild(el("p", { class: "muted", text: "Loading…" }));
  let doc;
  try { doc = await api.getDoc(target.db, target.col, target.id); }
  catch (e) { return renderError(e, target); }
  await renderArticle(pane, { ...target, doc: doc.document, rev: doc.rev }, {
    onNavigate: (t) => toArticle(t),
    onEdit: () => openEditor({ ...target, doc: doc.document, rev: doc.rev, isNew: false }),
    onHistory: () => openHistory(target),
    onShare: () => openShare(target),
    onDelete: (rev) => confirmDelete(target, rev),
  });
}

function renderError(e, target) {
  clear(pane);
  const msg = e instanceof ApiError && e.isForbidden ? `You do not have access to this ${T.document.one}.`
    : e instanceof ApiError && e.isNotFound ? `This ${T.document.one} does not exist.`
    : `Could not load this ${T.document.one}.`;
  const note = el("p", { class: "muted", text: msg });
  const actions = el("div", { class: "row-gap" });
  pane.appendChild(el("div", { class: "pane-toolbar" }, [
    el("span", { class: "crumbs", text: `${target.db} › ${target.col} › ${target.id}` }),
  ]));
  pane.append(note, actions);
  if (!(e instanceof ApiError && e.isNotFound)) return;

  actions.appendChild(el("button", {
    class: "btn secondary", type: "button", text: `Create this ${T.document.one}`,
    onclick: () => openEditor({ ...target, doc: {}, rev: null, isNew: true }),
  }));
  offerRestore(target, note, actions);
}

// A deleted article still answers for its history, so this page is the one place
// a writer can be standing when they most need it back — the chronos report and
// a stale link both send them here. Asked only after the read has 404'd, so a
// live article costs nothing.
async function offerRestore(target, note, actions) {
  let versions;
  try { versions = (await api.listVersions(target.db, target.col, target.id)).versions; }
  catch (err) { return; }  // never existed, or its history is gone with it
  const newest = versions[0];
  if (!newest || newest.op !== "delete") return;
  // Skip the tombstone: the version worth bringing back is the one before it.
  const restorable = versions.find((v) => v.op !== "delete");

  note.textContent = `Deleted by ${newest.author || "someone"} ${timeAgo(newest.timestamp)}.`;
  if (!restorable) {
    actions.appendChild(el("span", { class: "muted", text:
      "Its history has been pruned, so there is no version left to restore." }));
    return;
  }
  actions.insertBefore(el("button", {
    class: "btn", type: "button", text: "Restore",
    onclick: async () => {
      try { await api.restore(target.db, target.col, target.id, restorable.rev); }
      catch (err) { toast(err.message || "Could not restore it.", true); return; }
      toast(`Restored “${target.id}”.`);
      invalidate(target);
      browser.refresh(target.db, target.col);
      route();
    },
  }), actions.firstChild);
}

// -- writing -----------------------------------------------------------------

function openEditor(ctx) {
  renderEditor(pane, ctx, {
    // The editor does not know about namespaces: if this article's category
    // has not been made yet, that happens here, on the way to the first save.
    onCreate: async (document) => {
      if (ctx.pendingCollection) await ensureCollection(ctx.db, ctx.col);
      return api.createDoc(ctx.db, ctx.col, ctx.id, document);
    },
    onSaved: () => afterSave(ctx),
    onCancel: () => {
      if (!ctx.isNew) return openArticle(ctx);
      // Backing out of the first article in a brand-new category: that
      // category was never created, so there is no page of it to return to.
      return ctx.pendingCollection ? toDatabase(ctx.db) : toCollection(ctx.db, ctx.col);
    },
    onReload: () => openArticle(ctx),
    onCreateLink: (query, scopeOfLink) => createLinkTarget(query, scopeOfLink)
      .then((target) => { if (target) browser.refresh(target.db, target.col); return target; }),
  });
}

function afterSave(ctx) {
  invalidate(ctx);
  browser.refresh(ctx.db, ctx.col);
  const parts = parseHash();
  const alreadyHere = parts.length === 3
    && parts[0] === ctx.db && parts[1] === ctx.col && parts[2] === ctx.id;
  if (alreadyHere) route();
  else toArticle(ctx);
}

function openHistory(target) {
  renderHistory(pane, target, {
    onBack: () => openArticle(target),
    onRestored: () => { invalidate(target); openArticle(target); },
  });
}

function confirmDelete(target, rev) {
  modal({
    title: `Delete this ${T.document.one}?`,
    // Says where recovery lives, now that there is somewhere to point at.
    body: el("p", { text:
      `“${target.id}” will be removed from ${T.collection.many}, search and links. `
      + `Its history is kept: you can bring it back from the deleted list on this `
      + `${T.collection.one}'s page, or from this address.` }),
    actions: [
      { label: "Cancel", variant: "secondary" },
      { label: "Delete", variant: "danger", onClick: async (close) => {
          try {
            await api.deleteDoc(target.db, target.col, target.id, rev);
            toast(`${T.document.One} deleted.`);
            close();
            invalidate(target);
            browser.refresh(target.db, target.col);
            toCollection(target.db, target.col);
          } catch (e) { toast(e.message || "Delete failed.", true); }
        } },
    ],
  });
}

// -- create flows ------------------------------------------------------------

function newDatabase() {
  newDatabaseDialog({
    onCreated: (db, col) => { browser.load(); toCollection(db, col); },
  });
}

function newCollection(db) {
  newCollectionDialog(db, {
    onCreated: (col) => { browser.refresh(db); toCollection(db, col); },
  });
}

// The category is deliberately *not* created here — only when the article is
// saved — so backing out of the editor leaves nothing behind.
function newArticle(where = {}) {
  newArticleDialog({ db: where.db ?? scope.db, col: where.col ?? scope.col }, {
    onOpen: ({ db, col, id, title, pendingCollection }) => openEditor({
      db, col, id,
      doc: title ? { title } : {},
      rev: null, isNew: true, pendingCollection,
    }),
  });
}

// -- sharing -----------------------------------------------------------------

// Resolve (and cache) the logged-in username, so we can hide the owner from a
// resource's collaborator list.
let mePromise = null;
function currentUser() {
  if (!mePromise) mePromise = api.me().then((m) => m.username).catch(() => null);
  return mePromise;
}

// Manage who can access the current article or its collection, without leaving
// the editor. Reuses the same collaborator API the account page uses.
async function openShare(target) {
  const me = await currentUser();
  const roles = ["reader", "editor", "owner"];
  // Scope of what we're sharing: the article id, or null for the category.
  let scopeId = target.id;

  const scopeSel = el("select", {}, [
    el("option", { value: "doc", text: `This ${T.document.one} (${target.id})` }),
    el("option", { value: "col", text: `Whole ${T.collection.one} (${target.col})` }),
  ]);
  scopeSel.addEventListener("change", () => {
    scopeId = scopeSel.value === "doc" ? target.id : null;
    loadPeople();
  });

  const peopleBox = el("div", { class: "share-people" });
  const addRow = el("div", { class: "share-add" });
  const body = el("div", { class: "share-dialog" }, [
    el("div", { class: "field" }, [el("label", { text: "Sharing" }), scopeSel]),
    peopleBox,
    addRow,
  ]);

  async function buildAddRow() {
    clear(addRow);
    let contacts = [];
    try { contacts = (await api.contacts()).contacts; } catch (e) { /* leave empty */ }
    if (!contacts.length) {
      addRow.appendChild(el("p", { class: "muted" }, [
        "Add collaborators on your ",
        el("a", { href: "/account", text: "account page" }),
        " to share with them.",
      ]));
      return;
    }
    const userSel = el("select", {}, [
      el("option", { value: "", text: "Choose a collaborator…" }),
      ...contacts.map((c) => el("option", { value: c, text: c })),
    ]);
    const roleSel = el("select", {}, roles.map((r) => el("option", { value: r, text: r })));
    roleSel.value = "editor";
    const btn = el("button", { class: "btn sm", type: "button", text: "Share", onclick: async () => {
      const user = userSel.value;
      if (!user) return;
      try {
        await api.setCollaborator(target.db, target.col, scopeId, user, roleSel.value);
        userSel.value = "";
        await loadPeople();
      } catch (e) { toast(e.message || "Could not share.", true); }
    } });
    addRow.append(userSel, roleSel, btn);
  }

  async function loadPeople() {
    clear(peopleBox);
    peopleBox.appendChild(el("p", { class: "muted", text: "Loading…" }));
    let people;
    try { people = (await api.listCollaborators(target.db, target.col, scopeId)).collaborators; }
    catch (e) {
      clear(peopleBox);
      const msg = e instanceof ApiError && e.isForbidden
        ? "Only the owner can manage sharing here."
        : "Could not load sharing.";
      peopleBox.appendChild(el("p", { class: "muted", text: msg }));
      return;
    }
    people = people.filter((p) => p.username !== me);
    clear(peopleBox);
    if (!people.length) {
      peopleBox.appendChild(el("p", { class: "muted", text: "Not shared with anyone yet." }));
      return;
    }
    for (const c of people) {
      peopleBox.appendChild(el("div", { class: "person" }, [
        el("span", { class: "who" }, [el("strong", { text: c.username }), " ", el("span", { class: "chip", text: c.role })]),
        el("button", { class: "btn sm danger", type: "button", text: "Remove", onclick: async () => {
          try { await api.removeCollaborator(target.db, target.col, scopeId, c.username); await loadPeople(); }
          catch (e) { toast(e.message || "Could not remove.", true); }
        } }),
      ]));
    }
  }

  modal({ title: `Share “${target.id}”`, body, actions: [{ label: "Done", variant: "secondary" }] });
  buildAddRow();
  loadPeople();
}

// -- sidebar search (type-ahead over titles and slugs) -----------------------

let searchTimer = null;
let searchSeq = 0;

function initSearch() {
  const box = $("#search-box");
  const tree = $("#tree");
  box.addEventListener("input", () => {
    clearTimeout(searchTimer);
    const q = box.value.trim();
    if (!q) { browser.load(); return; }
    searchTimer = setTimeout(async () => {
      // Out-of-order guard: a slow early query must not overwrite a fast later
      // one and leave the wrong results on screen.
      const mine = ++searchSeq;
      let res;
      try { res = await api.suggest(q, scope.db, scope.col); } catch (e) { return; }
      if (mine !== searchSeq) return;
      clear(tree);
      for (const s of res.suggestions) {
        tree.appendChild(el("div", { class: "tree-node" }, [
          el("button", {
            class: "suggest-row", type: "button",
            onclick: () => toArticle({ db: s.database, col: s.collection, id: s.slug }),
          }, [
            el("span", { class: "suggest-title", text: s.title || s.slug }),
            // Which world this came from — two characters can share a name.
            el("span", { class: "suggest-scope muted", text: `${s.database_title} › ${s.collection_title}` }),
          ]),
        ]));
      }
      if (!res.suggestions.length) {
        tree.appendChild(el("div", { class: "tree-empty", text: "No matching titles." }));
      }
      tree.appendChild(el("button", {
        class: "tree-more", type: "button", text: `Search inside ${T.document.many} →`,
        onclick: () => { box.value = ""; toSearch(); },
      }));
    }, 200);
  });
}

// -- boot --------------------------------------------------------------------

function initChrome() {
  initTheme($("#theme-toggle"));
  initFontScale($("#font-toggle"));
  $("#menu-toggle").addEventListener("click", () => {
    const open = sidebar.classList.toggle("open");
    $("#scrim").hidden = !open;
  });
  $("#scrim").addEventListener("click", closeDrawer);
  $("#home-link").addEventListener("click", (e) => { e.preventDefault(); toHome(); });
  $("#new-article-btn").addEventListener("click", () => newArticle());
  initSearch();
}

initChrome();
browser.load();
window.addEventListener("hashchange", route);
route();
