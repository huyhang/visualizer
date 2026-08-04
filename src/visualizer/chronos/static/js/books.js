// The landing view: pick a book. Plotlines are scoped to a book, so the writer
// chooses one before seeing its plotline table.

import { api } from "./api.js";
import { clear, el } from "./dom.js";

function bookCard(book, onOpen) {
  const count = (book.plotlines || []).length;
  return el("button", { class: "book-card", onclick: () => onOpen(book.id) }, [
    el("div", { class: "book-card-head" }, [
      el("span", { class: "book-title", text: book.title || book.id }),
      el("span", { class: `status-pill ${book.status}`, text: book.status }),
    ]),
    el("div", { class: "book-sub", text: book.id }),
    el("div", { class: "book-meta", text: `${count} plotline${count === 1 ? "" : "s"}` }),
  ]);
}

export async function mountBooks(container, { onOpen }) {
  clear(container);
  const view = el("div", { class: "view books-view" }, [
    el("h1", { class: "view-title", text: "Your books" }),
    el("p", { class: "view-lead muted", text: "Choose a book to explore its plotlines." }),
  ]);
  container.appendChild(view);

  let data;
  try {
    data = await api.listBooks();
  } catch (e) {
    view.appendChild(el("p", { class: "empty", text: "Could not load your books." }));
    return;
  }
  const books = (data.books || []).slice().sort(
    (a, b) => (a.title || a.id).localeCompare(b.title || b.id),
  );
  if (!books.length) {
    view.appendChild(el("p", { class: "empty", text: "You have no readable books yet." }));
    return;
  }
  view.appendChild(el("div", { class: "book-grid" }, books.map((b) => bookCard(b, onOpen))));
}
