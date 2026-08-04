// The plotline table for one book: a paginated list ordered by name with a
// filter box that narrows to plotlines containing all the typed words. All the
// ordering/filtering/paging happens server-side (the /ui/plotlines helper); this
// view just drives it and renders rows.
//
// The last filter+page per book is remembered in-module, so returning from a
// plotline (via a breadcrumb or the browser Back button) lands back on the same
// filtered, paginated view the writer left.

import { api } from "./api.js";
import { clear, el, toast } from "./dom.js";

const PER_PAGE = 20;
const lastState = {}; // book -> { query, page }

function breadcrumb(bookTitle, onBooks) {
  return el("nav", { class: "crumbs" }, [
    el("a", { href: "#/", text: "Books", onclick: (e) => { e.preventDefault(); onBooks(); } }),
    el("span", { class: "sep", text: "›" }),
    el("span", { text: bookTitle }),
  ]);
}

function goalCells(goals) {
  return el("div", { class: "chip-row" }, (goals || []).map((g) => el("span", { class: "chip", text: g })));
}

function pager(data, onPage) {
  const { page, pages, total } = data;
  return el("div", { class: "pager" }, [
    el("button", { class: "btn secondary sm", text: "‹ Prev", disabled: page <= 1 ? "" : null,
      onclick: () => onPage(page - 1) }),
    el("span", { class: "pager-info", text: `Page ${page} of ${pages} · ${total} plotline${total === 1 ? "" : "s"}` }),
    el("button", { class: "btn secondary sm", text: "Next ›", disabled: page >= pages ? "" : null,
      onclick: () => onPage(page + 1) }),
  ]);
}

function table(rows, onOpen) {
  if (!rows.length) return el("p", { class: "empty", text: "No plotlines match your filter." });
  const body = rows.map((pl) => el("tr", { class: "pl-row", onclick: () => onOpen(pl.id) }, [
    el("td", {}, el("span", { class: "pl-name", text: pl.name })),
    el("td", {}, goalCells(pl.goals)),
  ]));
  return el("div", { class: "table-wrap" }, el("table", { class: "pl-table" }, [
    el("thead", {}, el("tr", {}, [el("th", { text: "Plotline" }), el("th", { text: "Goals" })])),
    el("tbody", {}, body),
  ]));
}

export async function mountPlotlineTable(container, book, { onOpen, onBooks }) {
  clear(container);
  const state = lastState[book] || { query: "", page: 1 };
  lastState[book] = state;

  let bookMeta = { title: book };
  try { bookMeta = await api.getBook(book); } catch (e) { /* fall back to id */ }

  const filterBox = el("input", {
    type: "search", class: "filter-box", placeholder: "Filter plotlines…",
    autocomplete: "off", value: state.query,
  });
  const results = el("div", { class: "pl-results" }, el("p", { class: "muted", text: "Loading…" }));

  container.appendChild(el("div", { class: "view table-view" }, [
    breadcrumb(bookMeta.title || book, onBooks),
    el("h1", { class: "view-title", text: bookMeta.title || book }),
    el("div", { class: "filter-bar" }, filterBox),
    results,
  ]));

  async function render() {
    try {
      const data = await api.listPlotlines(book, { filter: state.query, page: state.page, perPage: PER_PAGE });
      state.page = data.page; // server clamps out-of-range pages
      clear(results);
      results.appendChild(table(data.plotlines, onOpen));
      results.appendChild(pager(data, (p) => { state.page = p; render(); }));
    } catch (e) {
      clear(results);
      results.appendChild(el("p", { class: "empty", text: "Could not load plotlines." }));
      toast(e.message || "Could not load plotlines.", true);
    }
  }

  let debounce = null;
  filterBox.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { state.query = filterBox.value.trim(); state.page = 1; render(); }, 200);
  });

  render();
}
