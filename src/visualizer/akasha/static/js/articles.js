// One category's articles: a filtered, paginated table.
//
// The filter, the ordering and the paging all happen on the server, and the
// filter reaches the *whole* article rather than just its title — so this box
// is the field-and-text search the API always had and the browser never
// offered. This view is also where "New article" belongs: it already knows
// which category you mean, so it never asks.
//
// The last filter and page per category are remembered in-module, so coming
// back from an article (by breadcrumb or the Back button) lands on the same
// view you left rather than at the top of page one.

import { api } from "./api.js";
import { clear, el, toast } from "./dom.js";
import { confirmDeleteCollection } from "./create.js";
import { T, count } from "./terms.js";
import { crumbs, pager, timeAgo, viewHead } from "./views.js";

const PER_PAGE = 25;
const lastState = {}; // "db/col" -> { query, page }

// Arrive here already filtered. The tree hands off when more names match than
// it will show, and losing what you had typed on the way would be the whole
// point of the handoff wasted.
export function rememberFilter(database, collection, query) {
  lastState[`${database}/${collection}`] = { query: query || "", page: 1 };
}

function articleTable(rows, onOpen) {
  if (!rows.length) return el("p", { class: "empty", text: `No ${T.document.many} match.` });
  const body = rows.map((doc) => el("tr", { class: "list-row", onclick: () => onOpen(doc.id) }, [
    el("td", {}, el("span", { class: "list-name", text: doc.title || doc.id })),
    el("td", {}, el("code", { class: "list-slug", text: doc.id })),
    el("td", { class: "num", text: String(doc.rev ?? "") }),
    el("td", { class: "muted" }, [
      el("span", { text: timeAgo(doc.updated) }),
      doc.author ? el("span", { class: "list-author", text: ` by ${doc.author}` }) : null,
    ]),
  ]));
  return el("div", { class: "table-wrap" }, el("table", { class: "list-table" }, [
    el("thead", {}, el("tr", {}, [
      el("th", { text: "Title" }), el("th", { text: "Slug" }),
      el("th", { class: "num", text: "Rev" }), el("th", { text: "Updated" }),
    ])),
    el("tbody", {}, body),
  ]));
}

function deletedRow(doc, onRestore) {
  const when = doc.deleted_at ? timeAgo(doc.deleted_at) : "at some point";
  const by = doc.deleted_by ? ` by ${doc.deleted_by}` : "";
  return el("div", { class: "deleted-row" }, [
    el("span", { class: "deleted-name", text: doc.title || doc.id }),
    el("code", { class: "list-slug", text: doc.id }),
    el("span", { class: "muted deleted-when", text: `deleted${by} ${when}` }),
    doc.can_restore
      ? el("button", { class: "btn sm secondary", type: "button", text: "Restore",
                       onclick: () => onRestore(doc) })
      // Two different reasons the button is absent, and the writer needs to know
      // which: nothing left to bring back, or not theirs to bring back.
      : el("span", { class: "muted deleted-why", text:
          doc.restore_rev === null ? "history pruned" : "not yours to restore" }),
  ]);
}

// Deleted articles are hidden from every listing, which is right for reading and
// wrong for recovering: before this, getting one back meant already knowing its
// slug. Collapsed by default and loaded on demand — a recovery drawer, not part
// of the category.
function deletedSection(database, collection, total, onRestored) {
  const rows = el("div", { class: "deleted-rows" });
  rows.hidden = true;
  const label = (hidden) => `${count(total, T.document)} deleted — ${hidden ? "show" : "hide"}`;
  const toggle = el("button", { class: "tree-more", type: "button", text: label(true) });
  let loaded = false;

  async function load() {
    clear(rows);
    rows.appendChild(el("p", { class: "muted", text: "Loading…" }));
    let data;
    try { data = await api.listDeleted(database, collection); }
    catch (e) {
      clear(rows);
      rows.appendChild(el("p", { class: "muted", text: "Could not load these." }));
      return;
    }
    clear(rows);
    if (!data.documents.length) {
      rows.appendChild(el("p", { class: "muted", text: "Nothing here you can restore." }));
      return;
    }
    for (const doc of data.documents) {
      rows.appendChild(deletedRow(doc, async (target) => {
        try { await api.restore(database, collection, target.id, target.restore_rev); }
        catch (e) { toast(e.message || "Could not restore it.", true); return; }
        toast(`Restored “${target.title || target.id}”.`);
        onRestored();
      }));
    }
  }

  toggle.addEventListener("click", async () => {
    rows.hidden = !rows.hidden;
    toggle.textContent = label(rows.hidden);
    if (!rows.hidden && !loaded) { loaded = true; await load(); }
  });
  return el("div", { class: "deleted-section" }, [toggle, rows]);
}

export async function mountArticles(container, database, collection, handlers) {
  clear(container);
  const key = `${database}/${collection}`;
  const state = lastState[key] || { query: "", page: 1 };
  lastState[key] = state;

  const filterBox = el("input", {
    type: "search", class: "filter-box", placeholder: `Filter ${T.document.many}…`,
    autocomplete: "off", value: state.query,
  });
  const actions = el("div", { class: "view-actions" });
  const results = el("div", {}, [el("p", { class: "muted", text: "Loading…" })]);

  // The readable names come back with the listing; until then the slugs stand
  // in, so the page never flashes an empty heading or a gap where the trail is.
  const crumbBar = el("div", {});
  const heading = el("h1", { class: "view-title", text: collection });
  const showCrumbs = (world, category) => {
    clear(crumbBar);
    crumbBar.appendChild(crumbs([
      { label: "Home", onClick: handlers.onHome },
      { label: world, onClick: () => handlers.onDatabase(database) },
      { label: category },
    ]));
  };
  showCrumbs(database, collection);

  container.appendChild(el("div", { class: "view" }, [
    crumbBar,
    el("div", { class: "view-head" }, [heading, actions]),
    el("div", { class: "filter-bar" }, [filterBox]),
    results,
  ]));

  // The buttons depend on what the server says this user may do here, so they
  // are (re)drawn from each response rather than guessed at up front.
  function renderActions(data) {
    clear(actions);
    if (data.can_write) {
      actions.appendChild(el("button", {
        class: "btn sm", type: "button", text: `＋ New ${T.document.one}`,
        onclick: () => handlers.onCreate(database, collection),
      }));
    }
    // Only offered once no live article is left — the server refuses otherwise,
    // and a button that always fails is worse than no button. `deleted` is how
    // many tombstones remain, which the dialog has to warn about before they go.
    if (data.can_delete && data.total === 0 && !state.query) {
      actions.appendChild(el("button", {
        class: "btn sm danger", type: "button", text: `Delete ${T.collection.one}`,
        onclick: () => confirmDeleteCollection(database, collection, data.deleted, {
          onDeleted: (databaseRemoved) =>
            (databaseRemoved ? handlers.onHome() : handlers.onDatabase(database)),
        }),
      }));
    }
  }

  async function render() {
    let data;
    try {
      data = await api.listDocuments(database, collection,
        { filter: state.query, page: state.page, perPage: PER_PAGE });
    } catch (e) {
      const failed = `Could not load this ${T.collection.one}.`;
      clear(results);
      results.appendChild(el("p", { class: "empty", text: failed }));
      toast(e.message || failed, true);
      return;
    }
    state.page = data.page; // the server clamps an out-of-range page
    heading.textContent = data.collection_title;
    showCrumbs(data.database_title, data.collection_title);
    renderActions(data);
    clear(results);
    if (!data.total && !state.query) {
      results.appendChild(el("p", { class: "empty", text: `No ${T.document.many} here yet.` }));
    } else {
      results.appendChild(el("p", { class: "muted list-total", text: count(data.total, T.document) }));
      results.appendChild(articleTable(data.documents, (id) =>
        handlers.onArticle({ db: database, col: collection, id })));
    }
    const pages = pager(data, T.document, (p) => { state.page = p; render(); });
    if (pages) results.appendChild(pages);
    if (data.deleted) {
      results.appendChild(deletedSection(database, collection, data.deleted, () => {
        handlers.onRestored && handlers.onRestored(database, collection);
        render();
      }));
    }
  }

  let debounce = null;
  filterBox.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.query = filterBox.value.trim();
      state.page = 1;
      render();
    }, 200);
  });

  render();
}
