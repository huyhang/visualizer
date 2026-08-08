// The left-hand browse tree: worlds -> categories -> articles.
//
// The tree *navigates*; the category page *enumerates*. Keeping those apart is
// what makes this work at any size: the tree never has to show four hundred
// names, only make them reachable. So it holds itself to one invariant —
//
//     it never renders more than MAX_ROWS articles under a category,
//     whatever is typed —
//
// and hands off to the category page, carrying the query with it, the moment
// that stops being enough. The length of the sidebar is a property of the
// design rather than of your world.
//
// Above ~FILTER_ABOVE articles a category grows a filter box. It matches names
// only (`match=name`), unlike the full-text filter on the category page: a
// narrow column has nowhere to show *why* a body match matched, so those read
// as mystery hits, and one common word would return half the world. When more
// match than fit, the server has already ordered them best-first, so the twenty
// shown are the twenty most likely meant.
//
// It is also a real tree for the keyboard: arrows move, expand and collapse,
// with a roving tabindex, so it can be used without a mouse.

import { api } from "./api.js";
import { clear, el } from "./dom.js";
import { T, count } from "./terms.js";

const INLINE_LIMIT = 25;   // articles listed on expand, without being asked
const FILTER_ABOVE = 30;   // above this many, offer a filter box
const MAX_ROWS = 20;       // hard ceiling on rendered matches
const MIN_QUERY = 2;       // below this, one keystroke would match everything
const DEBOUNCE_MS = 200;

export class Browser {
  constructor(root, handlers) {
    this.root = root;
    this.handlers = handlers; // { onArticle, onDatabase, onCollection }
    this.active = null;       // "db/col/id" of the open article
    this.open = new Set();    // "db" and "db/col" of the expanded nodes
    this.nodes = new Map();   // the same keys -> { expand, reload }
    this.root.setAttribute("role", "tree");
    this.root.addEventListener("keydown", (e) => this._onKey(e));
  }

  async load() {
    clear(this.root);
    this.nodes.clear();
    this.root.appendChild(el("div", { class: "tree-loading", text: "Loading…" }));
    let data;
    try { data = await api.listDatabases(); }
    catch (e) { this._message("Failed to load."); return; }
    clear(this.root);
    if (!data.databases.length) {
      this._message(`No ${T.database.many} you can read yet.`);
      return;
    }
    for (const db of data.databases) this.root.appendChild(this._databaseNode(db));
    await this._restore();
    this._refreshTabStop();
  }

  // Re-read one branch without disturbing the rest. Falls back to the parent,
  // and then to a full reload, when the branch is not on screen yet — which is
  // what happens when the thing that changed is brand new.
  async refresh(db, col) {
    const node = (col && this.nodes.get(`${db}/${col}`)) || this.nodes.get(db);
    if (!node) return this.load();
    await node.reload();
    await this._restore();
    this._refreshTabStop();
  }

  // Unfold the tree down to an article and highlight it — so opening something
  // from a link, or from a fresh page load, shows you where it lives.
  async reveal({ db, col, id }) {
    this.setActive(`${db}/${col}/${id}`);
    await this.nodes.get(db)?.expand();
    await this.nodes.get(`${db}/${col}`)?.expand();
    this.setActive(`${db}/${col}/${id}`);
  }

  setActive(key) {
    this.active = key;
    for (const row of this.root.querySelectorAll(".tree-row.active")) {
      row.classList.remove("active");
      row.removeAttribute("aria-current");
    }
    const match = this.root.querySelector(`.tree-row[data-key="${CSS.escape(key)}"]`);
    if (match) {
      match.classList.add("active");
      match.setAttribute("aria-current", "page");
    }
    this._refreshTabStop();
  }

  // -- keyboard ---------------------------------------------------------------

  /** Every treeitem currently on screen, in the order the eye reads them. */
  _visibleRows() {
    return [...this.root.querySelectorAll('[role="treeitem"]')]
      .filter((row) => row.offsetParent !== null);
  }

  /** Exactly one row is tabbable, so Tab enters the tree and leaves it again
   *  rather than walking every branch. */
  _refreshTabStop() {
    const rows = this._visibleRows();
    if (!rows.length) return;
    const focused = rows.find((r) => r.classList.contains("active")) || rows[0];
    for (const row of rows) row.tabIndex = row === focused ? 0 : -1;
  }

  _focus(row) {
    if (!row) return;
    for (const other of this._visibleRows()) other.tabIndex = -1;
    row.tabIndex = 0;
    row.focus();
  }

  _onKey(event) {
    const row = event.target.closest('[role="treeitem"]');
    if (!row) return;
    const rows = this._visibleRows();
    const here = rows.indexOf(row);
    const node = this.nodes.get(row.dataset.node || "");
    const expanded = row.getAttribute("aria-expanded") === "true";

    const actions = {
      ArrowDown: () => this._focus(rows[here + 1]),
      ArrowUp: () => this._focus(rows[here - 1]),
      Home: () => this._focus(rows[0]),
      End: () => this._focus(rows[rows.length - 1]),
      // Right opens a closed branch, then walks into it; Left closes an open
      // one, then walks out. The standard treeview contract.
      ArrowRight: () => (node && !expanded ? node.expand() : this._focus(rows[here + 1])),
      ArrowLeft: () => (node && expanded ? node.collapse() : this._focus(this._parentRow(row))),
      Enter: () => row.dataset.open && this._activate(row),
      " ": () => (node ? (expanded ? node.collapse() : node.expand()) : this._activate(row)),
    };
    const action = actions[event.key];
    if (!action) return;
    event.preventDefault();
    action();
  }

  _parentRow(row) {
    const group = row.closest(".tree-node")?.parentElement?.closest(".tree-node");
    return group?.querySelector('[role="treeitem"]') || null;
  }

  _activate(row) {
    row.querySelector(".tree-label")?.click();
  }

  // -- internals -------------------------------------------------------------

  _message(text) {
    clear(this.root);
    this.root.appendChild(el("div", { class: "tree-empty", text }));
  }

  // Re-open whatever was expanded before, parents first so their children exist
  // by the time we reach them. A node that has since gone is simply skipped.
  async _restore() {
    const keys = [...this.open].sort((a, b) => a.split("/").length - b.split("/").length);
    for (const key of keys) await this.nodes.get(key)?.expand();
  }

  _forget(prefix) {
    for (const key of [...this.nodes.keys()]) {
      if (key.startsWith(prefix)) this.nodes.delete(key);
    }
  }

  // A branch: a twisty that loads its children on first use, and a label that
  // navigates to the level's own page. `loadChildren` is handed a `setCount` so
  // a branch that has just counted its children can correct the badge beside
  // its name, rather than showing the number from whenever the parent last
  // listed it.
  _branch({ key, level, label, meta, onOpen, loadChildren }) {
    const children = el("div", { class: "tree-children", role: "group" });
    children.hidden = true;
    const twisty = el("span", { class: "twisty", text: "+", "aria-hidden": "true" });
    const countEl = meta != null ? el("span", { class: "tree-count", text: String(meta) }) : null;
    const setCount = (n) => { if (countEl) countEl.textContent = String(n); };
    let loaded = false;

    const expand = async () => {
      children.hidden = false;
      twisty.textContent = "−";
      row.setAttribute("aria-expanded", "true");
      this.open.add(key);
      if (!loaded) { loaded = true; await loadChildren(children, setCount); }
      this._refreshTabStop();
    };
    const collapse = () => {
      children.hidden = true;
      twisty.textContent = "+";
      row.setAttribute("aria-expanded", "false");
      this.open.delete(key);
      this._refreshTabStop();
    };
    twisty.addEventListener("click", () => (children.hidden ? expand() : collapse()));

    this.nodes.set(key, {
      expand, collapse,
      reload: async () => { loaded = false; await expand(); },
    });

    const row = el("div", {
      class: `tree-row branch ${level}`, role: "treeitem", tabindex: "-1",
      "aria-expanded": "false", dataset: { node: key, open: "1" },
    }, [
      twisty,
      el("button", { class: "tree-label", type: "button", text: label, title: label,
                     tabindex: "-1", onclick: onOpen }),
      countEl,
    ]);
    return el("div", { class: "tree-node" }, [row, children]);
  }

  _databaseNode(db) {
    return this._branch({
      key: db.name,
      level: "level-database",
      label: db.title,
      // Always articles, at every level. The badge meaning one thing on a world
      // and another on a category is a small lie the eye has to decode.
      meta: db.articles,
      onOpen: () => this.handlers.onDatabase(db.name),
      loadChildren: async (container) => {
        this._forget(`${db.name}/`);
        await this._loadCollections(db.name, container);
      },
    });
  }

  async _loadCollections(db, container) {
    clear(container);
    container.appendChild(el("div", { class: "tree-loading", text: "…" }));
    let data;
    try { data = await api.listCollections(db); }
    catch (e) { clear(container); container.appendChild(el("div", { class: "tree-empty", text: "—" })); return; }
    clear(container);
    if (!data.collections.length) {
      container.appendChild(el("div", { class: "tree-empty", text: `No ${T.collection.many}.` }));
      return;
    }
    for (const col of data.collections) container.appendChild(this._collectionNode(db, col));
  }

  _collectionNode(db, col) {
    return this._branch({
      key: `${db}/${col.name}`,
      level: "level-collection",
      label: col.title,
      meta: col.articles,
      onOpen: () => this.handlers.onCollection(db, col.name),
      loadChildren: (container, setCount) =>
        this._loadArticles(db, col.name, container, setCount, col.articles),
    });
  }

  // One category's children: an optional filter, a bounded list, and an honest
  // way out when there is more than fits.
  async _loadArticles(db, col, container, setCount, known) {
    clear(container);
    const list = el("div", {});
    const filter = known > FILTER_ABOVE ? this._filterBox(db, col, list, setCount) : null;
    if (filter) container.appendChild(filter);
    container.appendChild(list);
    await this._fillArticles(db, col, list, setCount, "");
  }

  _filterBox(db, col, list, setCount) {
    const input = el("input", {
      type: "search", class: "tree-filter", autocomplete: "off",
      placeholder: `filter ${T.document.many} by name…`,
      "aria-label": `Filter ${T.document.many} by name`,
    });
    let timer = null;
    input.addEventListener("keydown", (e) => e.stopPropagation());  // arrows move the caret
    input.addEventListener("input", () => {
      clearTimeout(timer);
      const query = input.value.trim();
      // One character would match nearly everything; saying so beats answering.
      if (query.length === 1) return;
      timer = setTimeout(() => this._fillArticles(db, col, list, setCount, query), DEBOUNCE_MS);
    });
    return el("div", { class: "tree-filter-row" }, [input]);
  }

  async _fillArticles(db, col, container, setCount, query) {
    clear(container);
    container.appendChild(el("div", { class: "tree-loading", text: "…" }));
    const searching = query.length >= MIN_QUERY;
    let data;
    try {
      data = await api.listDocuments(db, col, {
        perPage: searching ? MAX_ROWS : INLINE_LIMIT,
        filter: searching ? query : undefined,
        match: searching ? "name" : undefined,
      });
    } catch (e) {
      clear(container);
      container.appendChild(el("div", { class: "tree-empty", text: "—" }));
      return;
    }
    clear(container);
    if (!searching) setCount(data.total);
    if (!data.documents.length) {
      container.appendChild(el("div", { class: "tree-empty", text:
        searching ? "No matching names." : `No ${T.document.many}.` }));
      if (searching) container.appendChild(this._seeAll(db, col, data.total, query));
      return;
    }
    for (const doc of data.documents) container.appendChild(this._articleNode(db, col, doc));
    if (data.total > data.documents.length) {
      container.appendChild(this._seeAll(db, col, data.total, query, data.documents.length));
    } else if (searching) {
      container.appendChild(el("div", { class: "tree-note", text:
        `${count(data.total, T.document)} match` }));
    }
  }

  // The way out. It carries the query, so the category page opens already
  // filtered — and widens it to the whole article, which is what that page is
  // for and what the sidebar deliberately is not.
  _seeAll(db, col, total, query, shown = 0) {
    const label = query
      ? (shown ? `${shown} of ${total} — see them all →` : `${total} elsewhere — see them all →`)
      : `${total - shown} more — see them all →`;
    return el("div", { class: "tree-node" }, [
      el("button", {
        class: "tree-more", type: "button", text: label,
        title: query ? "Opens the full list, including matches in article bodies" : null,
        onclick: () => this.handlers.onCollection(db, col, query),
      }),
    ]);
  }

  _articleNode(db, col, doc) {
    const key = `${db}/${col}/${doc.id}`;
    const label = doc.title || doc.id;
    const row = el("div", {
      class: "tree-row level-article", role: "treeitem", tabindex: "-1",
      dataset: { key, open: "1" },
    }, [
      el("span", { class: "twisty", text: "", "aria-hidden": "true" }),
      el("button", {
        class: "tree-label", type: "button", text: label, title: label, tabindex: "-1",
        onclick: () => this.handlers.onArticle({ db, col, id: doc.id }),
      }),
    ]);
    if (key === this.active) {
      row.classList.add("active");
      row.setAttribute("aria-current", "page");
    }
    return el("div", { class: "tree-node" }, [row]);
  }
}
