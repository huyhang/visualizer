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
import { calendarList } from "./calendarlist.js";
import { openCalendarForm } from "./calendarlibrary.js";
import { clear, el, toast } from "./dom.js";
import { confirmModal, modal } from "./picker.js";
import { slugify } from "./shared/slug.js";

// `book` is a GET /books/{id} response to edit, or null to create a new one.
// onDone(savedBook) fires after a successful write; onDeleted(id) after the book
// is gone, so the caller — which is the thing that knows where the writer was —
// decides where they land.
export async function openBookForm({ book = null, onDone, onDeleted } = {}) {
  const editing = book !== null;
  const state = {
    title: editing ? (book.title || "") : "",
    id: editing ? book.id : "",
    world: editing ? (book.world || "") : "",
    overview: editing ? (book.overview || "") : "",
  };
  // Asked for before the modal opens, so the chooser is never briefly empty and
  // the writer is never offered a world they cannot read.
  let worlds = [];
  try { worlds = (await api.listWorlds()).worlds || []; } catch (e) { /* offer none */ }
  // The writer's saved calendars, so the picker can offer them. Asked for up
  // front like the worlds are; a library we could not read simply offers none,
  // and the writer types a calendar in as they always could.
  let library = [];
  try { library = (await api.listCalendars()).calendars || []; } catch (e) { /* offer none */ }
  // Needed only to create a calendar under the right name if the writer builds
  // one from inside this form.
  let me = null;
  try { me = (await api.me()).username; } catch (e) { /* no create affordance */ }
  // A single world is the common case (one story, one canon) — take it as the
  // default rather than making the writer confirm the only option.
  if (!editing && worlds.length === 1) state.world = worlds[0].database;
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

  const calendars = calendarList({
    initial: editing ? (book.calendars || []) : [],
    library,
    // A writer with an empty library should not have to leave a half-filled
    // form to get one. This builds the calendar *in the library* — the book
    // still only ever names it — and hands it straight back to the row that
    // asked. The shared `library` array is refilled in place, so every other
    // row's picker sees the new calendar too.
    onCreateCalendar: me ? () => new Promise((resolve) => {
      openCalendarForm({
        me,
        onDone: async (made) => {
          try {
            const fresh = (await api.listCalendars()).calendars || [];
            library.splice(0, library.length, ...fresh);
          } catch (e) { /* keep what we have */ }
          resolve(library.find((c) => c.qualified_id === (made || {}).qualified_id) || null);
        },
      });
    }) : null,
    onChange: () => refresh(),
  });

  // The form is never rebuilt (only the problem list is), so this can keep its
  // own value and just report it to `state` as it is typed.
  const overviewBox = el("textarea", {
    rows: "3", placeholder: "What this book is about (optional)",
  });
  overviewBox.value = state.overview;
  overviewBox.addEventListener("input", () => { state.overview = overviewBox.value; });

  const view = el("form", { class: "book-form", onsubmit: save }, [
    field("Title", titleBox, "What you will call it. You can rename it later."),
    field("Id", idBox, editing
      ? "A book's id is permanent — it is what every link and grant points at."
      : "Used in links and in the API. Derived from the title until you change it."),
    field("Overview", overviewBox,
      "What the book is about, in your own words. No rule reads it; it is here so "
      + "a shelf of books says more than a row of titles."),
    worldField(),
    el("div", { class: "field" }, [
      el("label", { class: "field-label", text: "Time" }),
      el("p", { class: "field-hint muted", text: editing
        ? "Changing this re-labels the book — every scene keeps the tick it "
          + "already has, so no timing moves and no finding changes."
        : "How this book counts time. Scenes are always placed at whole-number "
          + "ticks; a calendar only decides how those numbers read back." }),
      el("p", { class: "field-hint muted", text:
        "A world may count time more than one way. Add a second calendar and "
        + "you can read the same scenes through either — the switcher above the "
        + "book lets you choose." }),
      calendars.node,
    ]),
    problemList,
    error,
    el("div", { class: "form-actions" }, [
      submit,
      el("button", { class: "btn secondary", type: "button", text: "Cancel", onclick: () => dialog.close() }),
      // Owners only, and never while creating — there is nothing to delete yet.
      editing && (book.permissions || {}).delete ? el("button", {
        class: "btn danger ghost", type: "button", text: "Delete book",
        onclick: confirmDelete,
      }) : null,
    ]),
    el("p", { class: "muted save-note", text: editing
      ? "Saving replaces the book's details; its plotlines and scenes are untouched."
      : "Nothing is written until you create it." }),
  ]);

  const dialog = modal(editing ? `Edit ${state.title || state.id}` : "New book",
    view, { wide: true }); // focuses the title box

  // Which Akasha world this book's cast, items and places come from. Without
  // one, a book with no scenes has nothing to point its pickers at — the scope
  // could only be inferred from scenes that do not exist yet, so the very first
  // scene form comes up empty.
  function worldField() {
    if (!worlds.length) {
      return field("World", el("p", { class: "muted", text:
        "You cannot read any worlds yet." }),
      "Create one in Articles first — a book's characters and places are articles there.");
    }
    const choose = el("select", {}, [
      el("option", { value: "", text: "— none yet —" }),
      ...worlds.map((w) => el("option", { value: w.database, text: w.database })),
    ]);
    choose.value = state.world;
    choose.addEventListener("change", () => { state.world = choose.value; refresh(); });
    return field("World", choose, worlds.length === 1
      ? "Where this book's characters, items and places live in Articles."
      : "Where this book's characters, items and places live. Scenes can still "
        + "reference another world; this is what the pickers search first.");
  }

  function problems() {
    const out = [];
    if (!state.title.trim()) out.push("Give the book a title.");
    if (!state.id) out.push("Give the book an id.");
    // Not required: a writer may plot before there is any canon to point at.
    // The scene form says so plainly when the time comes.
    return out.concat(calendars.problems());
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
  // field — not just the ones on screen. Omitting `terminus` here silently
  // un-designates the book's ending, which is the kind of loss a writer would
  // only notice much later, via a verdict that quietly stopped complaining; and
  // omitting `overview` would delete prose with nothing to hint that it went.
  function body() {
    const out = {
      title: state.title.trim(),
      overview: state.overview,
      // The list, never the older single `calendar` — the API refuses a body
      // carrying both, because which one the writer meant would be a guess.
      calendars: calendars.value(),
      world: state.world || null,
    };
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

  // -- deleting --------------------------------------------------------------

  // Deleting a book takes its plotlines and its scenes with it, hard, with no
  // history to restore from. So the confirmation is built from what is actually
  // in there rather than from a generic warning: a writer who is about to lose
  // seventeen scenes should be told the number seventeen.
  async function confirmDelete() {
    const { plotlines, scenes } = await contents();
    if (!plotlines && !scenes) {
      // Nothing to lose. A typing gate here would be theatre, and the codebase
      // already declines to scold an empty form for being empty.
      confirmModal(`Delete “${label()}”?`, "It has no plotlines or scenes yet.",
        { yes: "Delete", danger: true, onYes: doDelete });
      return;
    }
    askToType(plotlines, scenes);
  }

  // The plotline ids come with the book; the scene count is one cheap page of
  // one. A count we could not fetch is reported as unknown rather than as zero.
  async function contents() {
    const plotlines = (book.plotlines || []).length;
    try {
      return { plotlines, scenes: (await api.listEvents(state.id, { perPage: 1 })).total };
    } catch (e) {
      return { plotlines, scenes: null };
    }
  }

  function askToType(plotlines, scenes) {
    const typed = el("input", {
      type: "text", placeholder: state.id, autocomplete: "off", "aria-label": "Book id",
    });
    const go = el("button", { class: "btn danger", type: "button", text: "Delete this book" });
    go.disabled = true;
    typed.addEventListener("input", () => { go.disabled = typed.value.trim() !== state.id; });
    go.addEventListener("click", () => { dialog.close(); doDelete(); });

    const dialog = modal(`Delete “${label()}”?`, el("div", {}, [
      el("p", { text: `This deletes ${countPhrase(plotlines, scenes)} along with the book. It cannot be undone.` }),
      el("p", { class: "muted", text:
        "The characters, items and places its scenes reference are articles, and "
        + "are not touched." }),
      el("p", { text: `Type ${state.id} to confirm.` }),
      typed,
      el("div", { class: "form-actions" }, [
        go,
        el("button", { class: "btn secondary", type: "button", text: "Cancel",
          onclick: () => dialog.close() }),
      ]),
    ]));
  }

  async function doDelete() {
    try {
      await api.deleteBook(state.id, book.rev);
    } catch (e) {
      // Reported on the form, which is still open behind the confirmation.
      error.textContent = failure(e);
      error.hidden = false;
      return;
    }
    dialog.close();
    toast(`Deleted “${label()}”.`);
    if (onDeleted) onDeleted(state.id);
  }

  const label = () => state.title.trim() || state.id;

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

// "3 plotlines and 17 scenes", minus whatever is zero, and honest about a count
// that could not be read.
function countPhrase(plotlines, scenes) {
  const parts = [];
  if (plotlines) parts.push(`${plotlines} plotline${plotlines === 1 ? "" : "s"}`);
  if (scenes === null) parts.push("every scene in it");
  else if (scenes) parts.push(`${scenes} scene${scenes === 1 ? "" : "s"}`);
  return parts.join(" and ");
}

function field(label, control, hint) {
  return el("div", { class: "field" }, [
    el("label", { class: "field-label", text: label }),
    control,
    hint ? el("p", { class: "field-hint muted", text: hint }) : null,
  ]);
}
