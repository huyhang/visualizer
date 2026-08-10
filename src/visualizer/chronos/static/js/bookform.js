// The book form: write a new book, or change an existing one's title and
// calendar. One form for both, because they ask the same questions — only the
// id (permanent) and the verb differ.
//
// Creating a book was the one thing a writer could not do from the browser, and
// so the thing that made every other surface unreachable from a standing start.
//
// It is a modal for the same reason the plotline editor is: this is a detour
// from browsing, and cancelling should leave the list exactly as it was.
//
// The calendar deserves the room it takes up. It decides what a tick *means*
// everywhere downstream — what the timeline rail groups by, what the scene form
// reads back as you type — so a bare title field would quietly commit every book
// to plain integers. Editing it later is safe by construction: ticks are
// canonical integers and a calendar formats output only, so swapping one
// re-labels the book without moving a single scene or changing any verdict.

import { api } from "./api.js";
import { calendarField } from "./calendarfield.js";
import { clear, el, toast } from "./dom.js";
import { modal } from "./picker.js";
import { slugify } from "./shared/slug.js";

// `book` is a GET /books/{id} response to edit, or null to create a new one.
// onDone(savedBook) fires after a successful write.
export function openBookForm({ book = null, onDone } = {}) {
  const editing = book !== null;
  const state = {
    title: editing ? (book.title || "") : "",
    id: editing ? book.id : "",
  };
  // Nothing to auto-derive when the id is already fixed.
  let idTouched = editing;

  const titleBox = el("input", {
    type: "text", value: state.title, placeholder: "The Ember Pact", autocomplete: "off",
  });
  const idBox = el("input", {
    type: "text", value: state.id, placeholder: "ember-pact",
    autocomplete: "off", disabled: editing ? "" : null,
  });

  // The id follows the title until the writer takes it over. Book ids are
  // permanent and show up in every link, so they get a sensible default rather
  // than being hidden or generated behind the writer's back.
  titleBox.addEventListener("input", () => {
    state.title = titleBox.value;
    if (!idTouched) {
      idBox.value = slugify(titleBox.value);
      state.id = idBox.value;
    }
    refresh();
  });
  idBox.addEventListener("input", () => {
    idTouched = true;
    state.id = idBox.value.trim();
    refresh();
  });

  // Declared before the calendar field, so that everything `refresh` reads
  // exists by the time any change can reach it.
  const problemList = el("ul", { class: "form-error list", hidden: "" });
  const error = el("p", { class: "form-error", hidden: "" });
  const submit = el("button", {
    class: "btn", type: "submit", text: editing ? "Save changes" : "Create book",
  });

  const calendar = calendarField({
    initial: editing ? book.calendar : null,
    onChange: () => refresh(),
  });

  const view = el("form", { class: "book-form", onsubmit: save }, [
    field("Title", titleBox, "What you will call it. You can rename it later."),
    field("Id", idBox, editing
      ? "A book's id is permanent — it is what every link and grant points at."
      : "Used in links and in the API. Derived from the title until you change it."),
    el("div", { class: "field" }, [
      el("label", { class: "field-label", text: "Time" }),
      el("p", { class: "field-hint muted", text: editing
        ? "Changing this re-labels the book — every scene keeps the tick it "
          + "already has, so no timing moves and no finding changes."
        : "How this book counts time. Scenes are always placed at whole-number "
          + "ticks; a calendar only decides how those numbers read back." }),
      calendar.node,
    ]),
    problemList,
    error,
    el("div", { class: "form-actions" }, [
      submit,
      el("button", { class: "btn secondary", type: "button", text: "Cancel", onclick: () => dialog.close() }),
    ]),
    el("p", { class: "muted save-note", text: editing
      ? "Saving replaces the book's details; its plotlines and scenes are untouched."
      : "Nothing is written until you create it." }),
  ]);

  const dialog = modal(editing ? `Edit ${state.title || state.id}` : "New book",
    view, { wide: true }); // focuses the title box

  function problems() {
    const out = [];
    if (!state.title.trim()) out.push("Give the book a title.");
    if (!state.id) out.push("Give the book an id.");
    return out.concat(calendar.problems());
  }

  // Say what is missing, but only once the writer has started — an empty form
  // scolding you for being empty is noise. The button stays disabled either way,
  // so an untouched form cannot be submitted.
  function refresh() {
    const found = problems();
    const started = editing || Boolean(state.title.trim() || state.id);
    submit.disabled = found.length > 0;
    problemList.hidden = !found.length || !started;
    clear(problemList);
    for (const problem of found) problemList.appendChild(el("li", { text: problem }));
  }

  // PUT replaces the whole book document, so an edit has to resend every stored
  // field — not just the two on screen. Omitting `terminus` here silently
  // un-designates the book's ending, which is the kind of loss a writer would
  // only notice much later, via a verdict that quietly stopped complaining.
  function body() {
    const out = { title: state.title.trim(), calendar: calendar.value() };
    if (editing) out.terminus = book.terminus || null;
    return out;
  }

  async function save(event) {
    event.preventDefault();
    if (problems().length) return;
    error.hidden = true;
    submit.disabled = true;
    try {
      const saved = editing
        ? await api.updateBook(state.id, body(), book.rev)
        : await api.createBook(state.id, body());
      dialog.close();
      toast(editing ? "Book updated." : `Created “${saved.title || saved.id}”.`);
      if (onDone) onDone(saved);
    } catch (e) {
      error.textContent = failure(e);
      error.hidden = false;
      submit.disabled = false;
    }
  }

  function failure(e) {
    if (e.code === "ALREADY_EXISTS") {
      return `A book with the id “${state.id}” already exists. Choose another.`;
    }
    if (e.isConflict) {
      return "Someone else changed this book — reload the page before saving.";
    }
    return e.message || (editing ? "Could not save the book." : "Could not create the book.");
  }

  refresh();
  return dialog;
}

function field(label, control, hint) {
  return el("div", { class: "field" }, [
    el("label", { class: "field-label", text: label }),
    control,
    hint ? el("p", { class: "field-hint muted", text: hint }) : null,
  ]);
}
