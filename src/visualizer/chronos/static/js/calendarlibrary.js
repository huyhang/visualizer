// The calendar library: named reckonings a writer keeps and attaches to books.
//
// A route rather than a modal, and not book-scoped, because the whole point of
// a library is a calendar that outlives any one book. It reads like the scene
// library — a filtered list with per-row tools — and for the same reason: this
// is housekeeping, and closing it should put you back on the shelf.
//
// A calendar's identity is (owner, id). Names like "imperial" are generic
// enough that two writers will independently pick the same one, so nothing here
// assumes a slug is unique: rows show the owner whenever it is not you, and the
// same slug appearing twice is an ordinary state rather than a collision.
//
// Attaching happens in the *book* form, not here. This view builds and shares
// the calendars; a book copies one when it wants it.

import { api } from "./api.js";
import { clear, el, expandableText, field, headingAction, toast } from "./dom.js";
import { calendarHint } from "./calendars.js";
import { inlineCalendarEditor } from "./calendarfield.js";
import { confirmModal, modal } from "./picker.js";
import { slugify } from "./shared/slug.js";

let lastQuery = "";

export async function mountCalendarLibrary(container, { onBooks, me }) {
  clear(container);
  const results = el("div", { class: "calendar-results" },
    el("p", { class: "muted", text: "Loading…" }));
  const filterBox = el("input", {
    type: "search", class: "filter-box", placeholder: "Filter calendars…",
    autocomplete: "off", value: lastQuery,
  });

  container.appendChild(el("div", { class: "view calendars-view" }, [
    el("nav", { class: "crumbs" }, [
      el("a", { href: "#/", text: "Books", onclick: (e) => { e.preventDefault(); onBooks(); } }),
      el("span", { class: "sep", text: "›" }),
      el("span", { text: "Calendars" }),
    ]),
    el("div", { class: "books-head" }, [
      el("h1", { class: "view-title", text: "Your calendars" }),
      el("div", { class: "head-actions" }, [
        headingAction({
          label: "＋ New calendar", glyph: "plus",
          onClick: () => openCalendarForm({ me, onDone: render }),
        }),
      ]),
    ]),
    el("p", { class: "view-lead muted", text:
      "Reckonings you can attach to any book. A book copies the calendar it "
      + "attaches, so editing one here never re-dates a story you already wrote "
      + "— the book offers you the update instead." }),
    el("div", { class: "filter-bar" }, [filterBox]),
    results,
  ]));

  let debounce = null;
  filterBox.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { lastQuery = filterBox.value.trim(); render(); }, 200);
  });

  async function render() {
    let calendars;
    try {
      calendars = (await api.listCalendars()).calendars || [];
    } catch (e) {
      clear(results);
      results.appendChild(el("p", { class: "empty", text: "Could not load your calendars." }));
      return;
    }
    clear(results);
    const shown = calendars.filter((c) => matches(c, lastQuery));
    if (!calendars.length) {
      results.appendChild(el("div", { class: "empty-cta" }, [
        el("p", { class: "empty", text: "You have no saved calendars yet." }),
        el("p", { class: "muted", text:
          "Every book that counts time takes its calendar from here, so this is "
          + "the place to build one. A book with none simply shows plain ticks." }),
        el("button", {
          class: "btn", type: "button", text: "+ New calendar",
          onclick: () => openCalendarForm({ me, onDone: render }),
        }),
      ]));
      return;
    }
    if (!shown.length) {
      results.appendChild(el("p", { class: "empty", text: "No calendars match your filter." }));
      return;
    }
    results.appendChild(el("div", { class: "calendar-grid" },
      shown.map((c) => card(c, { me, onDone: render }))));
  }

  render();
}

function matches(calendar, query) {
  if (!query) return true;
  const haystack = `${calendar.name} ${calendar.qualified_id} ${calendar.notes}`.toLowerCase();
  return query.toLowerCase().split(/\s+/).every((word) => haystack.includes(word));
}

function card(calendar, { me, onDone }) {
  const mine = calendar.owner === me;
  return el("div", { class: "calendar-card" }, [
    el("div", { class: "calendar-card-head" }, [
      el("span", { class: "calendar-name", text: calendar.name }),
      // Only when it is not yours: qualifying your own calendars would be noise,
      // and this is exactly the mark that tells two same-named ones apart.
      mine ? null : el("span", { class: "chip", text: `shared by ${calendar.owner}` }),
    ].filter(Boolean)),
    el("div", { class: "book-sub", text: calendar.qualified_id }),
    // The plain-language reading, which is the only thing most writers need to
    // recognise a calendar by. No arithmetic here — see calendars.js.
    el("p", { class: "calendar-reading muted", text: calendarHint(calendar.descriptor) }),
    // Clamped so a grid of cards keeps one rhythm, but expandable: a note
    // explaining *why* a calendar was revised is the kind of thing a writer
    // needs in full, and it is exactly the kind that runs past two lines.
    calendar.notes ? expandableText(calendar.notes, { class: "book-overview" }) : null,
    el("div", { class: "row-tools" }, [
      mine ? el("button", {
        class: "icon-btn sm", type: "button", text: "✎", title: "Edit this calendar",
        onclick: () => openCalendarForm({ me, calendar, onDone }),
      }) : null,
      mine ? el("button", {
        class: "icon-btn sm", type: "button", text: "⇥", title: "Share this calendar",
        onclick: () => openShareForm(calendar, onDone),
      }) : null,
      mine ? el("button", {
        class: "icon-btn sm danger", type: "button", text: "✕", title: "Delete this calendar",
        onclick: () => confirmDelete(calendar, onDone),
      }) : null,
    ].filter(Boolean)),
  ].filter(Boolean));
}

// -- the form -----------------------------------------------------------------

export function openCalendarForm({ me, calendar = null, onDone } = {}) {
  const editing = calendar !== null;
  const state = {
    name: editing ? calendar.name : "",
    id: editing ? calendar.id : "",
    notes: editing ? calendar.notes : "",
  };
  let idTouched = editing;

  const nameBox = el("input", {
    type: "text", value: state.name, placeholder: "Imperial Reckoning", autocomplete: "off",
  });
  const idBox = el("input", {
    type: "text", value: state.id, placeholder: "imperial",
    autocomplete: "off", disabled: editing ? "" : null,
  });
  nameBox.addEventListener("input", () => {
    state.name = nameBox.value;
    if (!idTouched) { idBox.value = slugify(nameBox.value); state.id = idBox.value; }
    refresh();
  });
  idBox.addEventListener("input", () => {
    idTouched = true; state.id = idBox.value.trim(); refresh();
  });

  const notesBox = el("textarea", { rows: "2", placeholder: "What this calendar is for (optional)" });
  notesBox.value = state.notes;
  notesBox.addEventListener("input", () => { state.notes = notesBox.value; });

  const problemList = el("ul", { class: "form-error list", hidden: "" });
  const error = el("p", { class: "form-error", hidden: "" });
  const submit = el("button", {
    class: "btn", type: "submit", text: editing ? "Save changes" : "Create calendar",
  });

  // The bare editor, not the mode chooser: a library entry is always a real
  // calendar. "Plain numbers" is a book attaching nothing, and picking from the
  // library inside the library would be a circle.
  const editor = inlineCalendarEditor({
    initial: editing ? calendar.descriptor : null,
    onChange: () => refresh(),
  });

  const view = el("form", { class: "book-form", onsubmit: save }, [
    field("Name", nameBox, "What you will call it when attaching it to a book."),
    field("Id", idBox, editing
      ? "A calendar's id is permanent."
      : "Used in links. Derived from the name until you change it."),
    field("Notes", notesBox, "Anything worth remembering about this reckoning."),
    el("div", { class: "field" }, [
      el("label", { class: "field-label", text: "How it counts" }),
      editor.node,
    ]),
    problemList,
    error,
    el("div", { class: "form-actions" }, [
      submit,
      el("button", { class: "btn secondary", type: "button", text: "Cancel",
        onclick: () => dialog.close() }),
    ]),
    el("p", { class: "muted save-note", text: editing
      ? "Books that already use this calendar keep the copy they took. They will "
        + "be offered the change; none of them is re-dated behind your back."
      : "Nothing is written until you create it." }),
  ]);

  const dialog = modal(editing ? `Edit ${state.name || state.id}` : "New calendar",
    view, { wide: true });

  function problems() {
    const out = [];
    if (!state.name.trim()) out.push("Give the calendar a name.");
    if (!state.id) out.push("Give the calendar an id.");
    return out.concat(editor.problems());
  }

  function refresh() {
    const found = problems();
    const started = editing || Boolean(state.name.trim() || state.id);
    submit.disabled = found.length > 0;
    problemList.hidden = !found.length || !started;
    clear(problemList);
    for (const problem of found) problemList.appendChild(el("li", { text: problem }));
  }

  async function save(event) {
    event.preventDefault();
    if (problems().length) return;
    error.hidden = true;
    submit.disabled = true;
    const body = { name: state.name.trim(), notes: state.notes, descriptor: editor.value() };
    try {
      const saved = editing
        ? await api.updateCalendar(calendar.owner, calendar.id, body, calendar.rev)
        : await api.createCalendar(me, state.id, body);
      dialog.close();
      toast(editing ? "Calendar updated." : `Created “${state.name.trim()}”.`);
      // Handed back, so a caller that opened this to fill a gap — the book
      // form's "＋ New calendar" — can select it without re-reading the list.
      if (onDone) onDone(saved);
    } catch (e) {
      error.textContent = failure(e, state.id, editing);
      error.hidden = false;
      submit.disabled = false;
    }
  }

  refresh();
  return dialog;
}

function failure(e, id, editing) {
  if (e.code === "ALREADY_EXISTS") {
    return `You already have a calendar with the id “${id}”. Choose another.`;
  }
  if (e.isConflict) return "Someone else changed this calendar — reload before saving.";
  return e.message || (editing ? "Could not save the calendar." : "Could not create it.");
}

// -- sharing ------------------------------------------------------------------

function openShareForm(calendar, onDone) {
  const who = el("input", { type: "text", placeholder: "username", autocomplete: "off" });
  const role = el("select", {}, [
    el("option", { value: "reader", text: "Reader — may attach it to their books" }),
    el("option", { value: "editor", text: "Editor — may also change it" }),
  ]);
  const error = el("p", { class: "form-error", hidden: "" });

  async function share() {
    const username = who.value.trim();
    if (!username) return;
    try {
      await api.shareCalendar(calendar.owner, calendar.id, username, role.value);
      dialog.close();
      toast(`Shared “${calendar.name}” with ${username}.`);
      if (onDone) onDone();
    } catch (e) {
      error.textContent = e.message || "Could not share this calendar.";
      error.hidden = false;
    }
  }

  const dialog = modal(`Share “${calendar.name}”`, el("div", {}, [
    el("p", { class: "muted", text:
      "They will see it in their own library, beside any calendar of their own "
      + "that happens to share its name." }),
    field("Writer", who, null),
    field("They may", role, null),
    error,
    el("div", { class: "form-actions" }, [
      el("button", { class: "btn", type: "button", text: "Share", onclick: share }),
      el("button", { class: "btn secondary", type: "button", text: "Cancel",
        onclick: () => dialog.close() }),
    ]),
  ]));
  return dialog;
}

function confirmDelete(calendar, onDone) {
  confirmModal(`Delete “${calendar.name}”?`,
    "Books that already use it keep working — each one holds its own copy of the "
    + "calendar, so nothing is re-dated. They simply stop being offered updates "
    + "from this entry.",
    {
      yes: "Delete", danger: true,
      onYes: async () => {
        try {
          await api.deleteCalendar(calendar.owner, calendar.id, calendar.rev);
          toast(`Deleted “${calendar.name}”.`);
          if (onDone) onDone();
        } catch (e) {
          toast(e.message || "Could not delete the calendar.", true);
        }
      },
    });
}
