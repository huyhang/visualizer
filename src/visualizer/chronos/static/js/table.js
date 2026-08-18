// The plotline table for one book: a paginated list ordered by name with a
// filter box that narrows to plotlines containing all the typed words. All the
// ordering/filtering/paging happens server-side (the /ui/plotlines helper); this
// view just drives it and renders rows.
//
// The last filter+page per book is remembered in-module, so returning from a
// plotline (via a breadcrumb or the browser Back button) lands back on the same
// filtered, paginated view the writer left.

import { api } from "./api.js";
import { openBookForm } from "./bookform.js";
import { clear, el, toast } from "./dom.js";
import { pager } from "./paging.js";
import { openPlotlineEditor } from "./plotedit.js";

const PER_PAGE = 20;
const lastState = {}; // book -> { query, page }

function breadcrumb(bookTitle, onBooks) {
  return el("nav", { class: "crumbs" }, [
    el("a", { href: "#/", text: "Books", onclick: (e) => { e.preventDefault(); onBooks(); } }),
    el("span", { class: "sep", text: "›" }),
    el("span", { text: bookTitle }),
  ]);
}

// Each goal a thread serves, as a chip that opens the goal. Clicks stop there
// rather than falling through to the row, which would open the plotline instead
// of the thing that was clicked.
function goalCells(goals, onGoals) {
  return el("div", { class: "chip-row" }, (goals || []).map((g) => (g.missing
    ? el("span", { class: "chip missing", text: g.title, title: "No longer in this book" })
    : el("button", {
        class: "chip link", type: "button", text: g.title, title: "Open this goal",
        onclick: (e) => { e.stopPropagation(); onGoals(g.id); },
      }))));
}

// How many problems this thread has (server-counted, so it matches what the
// plotline view will say). Silent when there are none: a column of green ticks
// would be noise, and its absence is already the signal.
function healthCell(count) {
  if (!count) return el("span", { class: "muted", text: "—" });
  return el("span", {
    class: "health-flag",
    title: "Open the plotline to see what is wrong.",
    text: `${count} problem${count === 1 ? "" : "s"}`,
  });
}

function table(rows, onOpen, onGoals) {
  if (!rows.length) return el("p", { class: "empty", text: "No plotlines match your filter." });
  const body = rows.map((pl) => el("tr", { class: "pl-row", onclick: () => onOpen(pl.id) }, [
    el("td", {}, [
      el("span", { class: "pl-name", text: pl.name }),
      // Under the name rather than in a column of its own: it is prose, and a
      // column of prose would squeeze the two that are scannable.
      pl.overview ? el("p", { class: "row-overview", text: pl.overview }) : null,
    ]),
    el("td", {}, goalCells(pl.goals, onGoals)),
    el("td", {}, healthCell(pl.conflicts)),
  ]));
  return el("div", { class: "table-wrap" }, el("table", { class: "pl-table" }, [
    el("thead", {}, el("tr", {}, [
      el("th", { text: "Plotline" }), el("th", { text: "Goals" }), el("th", { text: "Health" }),
    ])),
    el("tbody", {}, body),
  ]));
}

export async function mountPlotlineTable(container, book, { onOpen, onBooks, onScenes, onGoals, onIssues, onMap }) {
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

  const canWrite = Boolean((bookMeta.permissions || {}).write);
  const conflicted = bookMeta.status === "conflicted";

  // How many, not just whether — the button's whole job is to say if it is worth
  // opening. Two things keep it cheap. It is filled in *after* the page is on
  // screen, so the table never waits on a whole-book pass for a label; and it is
  // only asked for at all when the book is already known to be conflicted, since
  // a sound book has no count to show.
  const reportButton = el("button", {
    class: `btn ${conflicted ? "danger ghost" : "secondary"} sm`,
    type: "button", text: "Report",
    title: "Everything wrong across this book's plotlines",
    onclick: onIssues,
  });
  if (conflicted) {
    api.bookIssues(book)
      .then(({ summary }) => {
        const n = summary.problems;
        if (n) reportButton.textContent = `Report · ${n} problem${n === 1 ? "" : "s"}`;
      })
      .catch(() => { /* the plain label is a fine answer */ });
  }

  container.appendChild(el("div", { class: "view table-view" }, [
    breadcrumb(bookMeta.title || book, onBooks),
    el("div", { class: "book-head" }, [
      el("h1", { class: "view-title", text: bookMeta.title || book }),
      // The book's own details live here rather than on the books grid: this is
      // the only screen that is *about* one book, and the calendar it edits is
      // what every timestamp below is written in.
      canWrite ? el("button", {
        class: "icon-btn sm", type: "button", text: "✎",
        title: "Rename this book or change its calendar",
        onclick: () => openBookForm({
          book: bookMeta,
          // Remount rather than patch the heading: the calendar may have
          // changed, and every tick label on the page is written in it.
          onDone: () => mountPlotlineTable(container, book, { onOpen, onBooks, onScenes, onGoals, onIssues, onMap }),
          // This view is *about* the book that just stopped existing, so there
          // is nothing here to return to.
          onDeleted: onBooks,
        }),
      }) : null,
      // The book's scenes, as a list of their own. Offered to readers too:
      // browsing what happens in a book is not an editing act, and the library
      // hides its own write controls without the grant for them.
      el("button", {
        class: "btn secondary sm", type: "button", text: "Scenes",
        title: "Every scene in this book — write, edit or remove them",
        onclick: onScenes,
      }),
      // What the threads below are *for*, and what rests on what. The Goals
      // column says which ones a thread serves; this is where they are written,
      // and where the book answers whether it delivers them.
      el("button", {
        class: "btn secondary sm", type: "button", text: "Goals",
        title: "What this book is trying to bring about",
        onclick: () => onGoals(),
      }),
      // How the threads below actually weave: pick any number of them and see
      // where they meet. The table says what the threads *are*, one per row;
      // this is the one screen that says how they relate to each other.
      el("button", {
        class: "btn secondary sm", type: "button", text: "Story Map",
        title: "Draw any number of these threads together, laid out by time",
        onclick: onMap,
      }),
      // The Health column below says which threads have problems; this says what
      // they are, across all of them at once — including the ones no single
      // thread can explain, like a book with no ending designated. Marked when
      // the book is already known to be conflicted, so the writer does not have
      // to open it to find out whether it is worth opening.
      reportButton,
    ].filter(Boolean)),
    // What the book is about, under its title — the one screen that is about
    // this book and nothing else is where its summary belongs.
    bookMeta.overview ? el("p", { class: "view-lead overview", text: bookMeta.overview }) : null,
    el("div", { class: "filter-bar" }, [
      filterBox,
      canWrite
        ? el("button", {
            class: "btn sm", type: "button", text: "+ New plotline",
            // A modal, so the filter and page you were on survive the detour.
            onclick: () => openPlotlineEditor(book, null, {
              after: ({ saved }) => { if (saved) render(); },
            }),
          })
        : null,
    ].filter(Boolean)),
    results,
  ]));

  async function render() {
    try {
      const data = await api.listPlotlines(book, { filter: state.query, page: state.page, perPage: PER_PAGE });
      state.page = data.page; // server clamps out-of-range pages
      clear(results);
      results.appendChild(table(data.plotlines, onOpen, onGoals));
      results.appendChild(pager(data, (p) => { state.page = p; render(); }, { noun: "plotline" }));
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
