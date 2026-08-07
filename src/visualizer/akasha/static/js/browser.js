// The left-hand browse tree: worlds -> categories -> articles, lazily
// loaded and already grant-filtered by the server.
//
// The tree is a shortcut, not the only way in — every level it shows also has a
// page of its own, so clicking a *name* opens that page while the twisty beside
// it expands in place. Three things it is careful about:
//
//   - it remembers what you had open, so saving an article no longer collapses
//     everything you had unfolded;
//   - it refreshes one category rather than rebuilding from the root;
//   - it never truncates silently: what it cannot fit is offered as a link to
//     the full, paginated list.

import { api } from "./api.js";
import { clear, el } from "./dom.js";
import { T } from "./terms.js";

const TREE_LIMIT = 50; // articles shown inline before deferring to the list page

export class Browser {
  constructor(root, handlers) {
    this.root = root;
    this.handlers = handlers; // { onArticle, onDatabase, onCollection }
    this.active = null;       // "db/col/id" of the open article
    this.open = new Set();    // "db" and "db/col" of the expanded nodes
    this.nodes = new Map();   // the same keys -> { expand, reload }
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
  }

  // Re-read one branch without disturbing the rest. Falls back to the parent,
  // and then to a full reload, when the branch is not on screen yet — which is
  // what happens when the thing that changed is brand new.
  async refresh(db, col) {
    const node = (col && this.nodes.get(`${db}/${col}`)) || this.nodes.get(db);
    if (!node) return this.load();
    await node.reload();
    await this._restore();
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
    for (const row of this.root.querySelectorAll(".tree-row.active")) row.classList.remove("active");
    this.root.querySelector(`.tree-row[data-key="${CSS.escape(key)}"]`)?.classList.add("active");
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
  _branch({ key, label, meta, onOpen, loadChildren }) {
    const children = el("div", { class: "tree-children" });
    children.hidden = true;
    const twisty = el("span", { class: "twisty", text: "▸", role: "button", "aria-label": "Expand" });
    const countEl = meta != null ? el("span", { class: "tree-count", text: String(meta) }) : null;
    const setCount = (n) => { if (countEl) countEl.textContent = String(n); };
    let loaded = false;

    const expand = async () => {
      children.hidden = false;
      twisty.textContent = "▾";
      this.open.add(key);
      if (!loaded) { loaded = true; await loadChildren(children, setCount); }
    };
    const collapse = () => {
      children.hidden = true;
      twisty.textContent = "▸";
      this.open.delete(key);
    };
    twisty.addEventListener("click", () => (children.hidden ? expand() : collapse()));

    this.nodes.set(key, {
      expand,
      reload: async () => { loaded = false; await expand(); },
    });

    const row = el("div", { class: "tree-row branch" }, [
      twisty,
      el("button", { class: "tree-label", type: "button", text: label, onclick: onOpen }),
      countEl,
    ]);
    return el("div", { class: "tree-node" }, [row, children]);
  }

  _databaseNode(db) {
    return this._branch({
      key: db.name,
      label: db.title,
      meta: db.collections,
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
      label: col.title,
      meta: col.articles,
      onOpen: () => this.handlers.onCollection(db, col.name),
      loadChildren: (container, setCount) => this._loadArticles(db, col.name, container, setCount),
    });
  }

  async _loadArticles(db, col, container, setCount) {
    clear(container);
    container.appendChild(el("div", { class: "tree-loading", text: "…" }));
    let data;
    try { data = await api.listDocuments(db, col, { perPage: TREE_LIMIT }); }
    catch (e) { clear(container); container.appendChild(el("div", { class: "tree-empty", text: "—" })); return; }
    clear(container);
    setCount(data.total);
    if (!data.documents.length) {
      container.appendChild(el("div", { class: "tree-empty", text: `No ${T.document.many}.` }));
      return;
    }
    for (const doc of data.documents) container.appendChild(this._articleNode(db, col, doc));
    const hidden = data.total - data.documents.length;
    if (hidden > 0) {
      container.appendChild(el("div", { class: "tree-node" }, [
        el("button", {
          class: "tree-more", type: "button", text: `${hidden} more…`,
          onclick: () => this.handlers.onCollection(db, col),
        }),
      ]));
    }
  }

  _articleNode(db, col, doc) {
    const key = `${db}/${col}/${doc.id}`;
    const row = el("div", { class: "tree-row", dataset: { key } }, [
      el("span", { class: "twisty", text: "·" }),
      el("button", {
        class: "tree-label", type: "button", text: doc.title || doc.id,
        onclick: () => this.handlers.onArticle({ db, col, id: doc.id }),
      }),
    ]);
    if (key === this.active) row.classList.add("active");
    return el("div", { class: "tree-node" }, [row]);
  }
}
