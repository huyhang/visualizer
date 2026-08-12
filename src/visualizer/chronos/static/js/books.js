// The landing view: pick a book, or write one. Plotlines are scoped to a book,
// so the writer chooses one before seeing its plotline table.
//
// Any authenticated user may create a book and owns what they create, so unlike
// the plotline table this view has no permission to check before offering it —
// there is nothing to hold a grant on until the book exists.

import { api } from "./api.js";
import { openBookForm } from "./bookform.js";
import { clear, el } from "./dom.js";

function bookCard(book, onOpen) {
  const count = (book.plotlines || []).length;
  return el("button", { class: "book-card", onclick: () => onOpen(book.id) }, [
    el("div", { class: "book-card-head" }, [
      el("span", { class: "book-title", text: book.title || book.id }),
      el("span", { class: `status-pill ${book.status}`, text: book.status }),
    ]),
    el("div", { class: "book-sub", text: book.id }),
    // What the book is about, clamped to a couple of lines so the cards keep a
    // common height — the shelf reads as a shelf, not a wall of prose.
    book.overview ? el("p", { class: "book-overview", text: book.overview }) : null,
    el("div", { class: "book-meta", text: `${count} plotline${count === 1 ? "" : "s"}` }),
  ]);
}

function newBookButton(onOpen, { primary = false } = {}) {
  return el("button", {
    class: `btn${primary ? "" : " secondary"} sm`, type: "button", text: "+ New book",
    // Straight into it: a new book's whole point is the plotline you are about
    // to write, and that is one screen further in.
    onclick: () => openBookForm({ onDone: (saved) => onOpen(saved.id) }),
  });
}

export async function mountBooks(container, { onOpen, onCalendars }) {
  clear(container);
  const results = el("div", { class: "book-results" },
    el("p", { class: "muted", text: "Loading…" }));

  container.appendChild(el("div", { class: "view books-view" }, [
    el("div", { class: "books-head" }, [
      el("h1", { class: "view-title", text: "Your books" }),
      // Reachable from the shelf rather than from inside a book, because a
      // calendar belongs to no book in particular — and the writer wants one
      // ready *before* creating the book that will use it.
      el("button", {
        class: "btn secondary sm", type: "button", text: "Calendars",
        title: "Reckonings you can attach to any book",
        onclick: onCalendars,
      }),
      newBookButton(onOpen),
    ]),
    el("p", { class: "view-lead muted", text: "Choose a book to explore its plotlines." }),
    results,
  ]));

  let data;
  try {
    data = await api.listBooks();
  } catch (e) {
    clear(results);
    results.appendChild(el("p", { class: "empty", text: "Could not load your books." }));
    return;
  }

  const books = (data.books || []).slice().sort(
    (a, b) => (a.title || a.id).localeCompare(b.title || b.id),
  );
  clear(results);
  if (!books.length) {
    // The first thing a new writer sees. It used to be a dead end.
    results.appendChild(el("div", { class: "empty-cta" }, [
      el("p", { class: "empty", text: "You have no books yet." }),
      newBookButton(onOpen, { primary: true }),
    ]));
    return;
  }
  results.appendChild(el("div", { class: "book-grid" }, books.map((b) => bookCard(b, onOpen))));
}
