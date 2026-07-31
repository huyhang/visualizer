// The left-hand browse tree: databases -> collections -> documents, lazily
// loaded and already grant-filtered by the server.

import { api, ApiError } from "./api.js";
import { $, el, clear, toast } from "./dom.js";

export class Browser {
  constructor(root, { onOpen }) {
    this.root = root;
    this.onOpen = onOpen;
    this.active = null; // "db/col/id" of the open article
  }

  async load() {
    clear(this.root);
    this.root.appendChild(el("div", { class: "tree-loading", text: "Loading…" }));
    let data;
    try { data = await api.listDatabases(); }
    catch (e) { clear(this.root); this.root.appendChild(el("div", { class: "tree-empty", text: "Failed to load." })); return; }
    clear(this.root);
    if (!data.databases.length) {
      this.root.appendChild(el("div", { class: "tree-empty", text: "No databases you can read yet." }));
      return;
    }
    for (const db of data.databases) this.root.appendChild(this._dbNode(db));
  }

  _dbNode(db) {
    const children = el("div", { class: "tree-children" }, []);
    children.hidden = true;
    let loaded = false;
    const row = this._row("▸", db, "database", async (twisty) => {
      children.hidden = !children.hidden;
      twisty.textContent = children.hidden ? "▸" : "▾";
      if (!loaded && !children.hidden) {
        loaded = true;
        await this._loadCollections(db, children);
      }
    });
    return el("div", { class: "tree-node" }, [row, children]);
  }

  async _loadCollections(db, container) {
    container.appendChild(el("div", { class: "tree-loading", text: "…" }));
    let data;
    try { data = await api.listCollections(db); }
    catch (e) { clear(container); container.appendChild(el("div", { class: "tree-empty", text: "—" })); return; }
    clear(container);
    if (!data.collections.length) {
      container.appendChild(el("div", { class: "tree-empty", text: "No collections." }));
      return;
    }
    for (const col of data.collections) container.appendChild(this._colNode(db, col));
  }

  _colNode(db, col) {
    const children = el("div", { class: "tree-children" }, []);
    children.hidden = true;
    let loaded = false;
    const reload = async () => { await this._loadDocuments(db, col, children); };
    const row = this._row("▸", col, "collection", async (twisty) => {
      children.hidden = !children.hidden;
      twisty.textContent = children.hidden ? "▸" : "▾";
      if (!loaded && !children.hidden) { loaded = true; await reload(); }
    });
    const node = el("div", { class: "tree-node" }, [row, children]);
    node._reload = async () => { loaded = true; children.hidden = false; row.querySelector(".twisty").textContent = "▾"; await reload(); };
    node._db = db; node._col = col;
    return node;
  }

  async _loadDocuments(db, col, container) {
    container.appendChild(el("div", { class: "tree-loading", text: "…" }));
    let data;
    try { data = await api.listDocuments(db, col); }
    catch (e) { clear(container); container.appendChild(el("div", { class: "tree-empty", text: "—" })); return; }
    clear(container);
    if (!data.documents.length) {
      container.appendChild(el("div", { class: "tree-empty", text: "No articles." }));
      return;
    }
    for (const doc of data.documents) {
      const key = `${db}/${col}/${doc.id}`;
      const row = this._row("·", doc.title || doc.id, null, () => this.onOpen({ db, col, id: doc.id }));
      row.dataset.key = key;
      if (key === this.active) row.classList.add("active");
      container.appendChild(el("div", { class: "tree-node" }, [row]));
    }
  }

  _row(twisty, label, kind, onClick) {
    const tw = el("span", { class: "twisty", text: twisty });
    const row = el("div", { class: "tree-row" }, [
      tw,
      el("span", { text: label }),
      kind ? el("span", { class: "kind", text: kind === "database" ? "" : "" }) : null,
    ]);
    row.addEventListener("click", () => onClick(tw));
    return row;
  }

  setActive(key) {
    this.active = key;
    for (const row of this.root.querySelectorAll(".tree-row.active")) row.classList.remove("active");
    const match = this.root.querySelector(`.tree-row[data-key="${CSS.escape(key)}"]`);
    if (match) match.classList.add("active");
  }
}
