// The book form's list of attached calendars.
//
// A book may keep more than one reckoning at a time, because a world may. The
// Imperial calendar runs the length of the story; the Elvish one stops when the
// elves do. Both date the same scenes, and the writer reads through whichever
// one they want — nothing about the story changes, only the labels.
//
// Its contract is the same shape as one calendar field's:
//   `value() -> attachment[]` and `problems() -> string[]`.
//
// An attachment *names* a library calendar and says how this book uses it — the
// label it goes by, the span of ticks its culture kept it for, and for an Earth
// calendar which moment this book's tick 0 was. It never carries the calendar
// itself; the server reads that from the library.
//
// The common case is one row, and it should still feel like one field: an
// unnamed single calendar shows no id box, no era box and no remove button.
// Everything extra appears only once there is a second reckoning to tell apart.

import { clear, el, field } from "./dom.js";
import { calendarField } from "./calendarfield.js";
import { slugify } from "./shared/slug.js";

// Matches the server's cap (`validation.MAX_CALENDARS`). Kept in step by being
// stated once here and refused there — the browser is never the only guard.
const MAX = 8;
const DEFAULT_ID = "default";

export function calendarList({
  initial = [], library = [], onCreateCalendar = null, onChange = () => {},
} = {}) {
  // Each row owns its own field; the list owns their order and their ids.
  const rows = (initial.length ? initial : [blank()]).map((a) => row(a));
  const body = el("div", { class: "calendar-rows" });
  const addButton = el("button", {
    class: "btn secondary sm", type: "button", text: "+ Add another calendar",
    title: "A second reckoning over the same scenes — another culture's count",
    onclick: () => { rows.push(row(blank())); rebuild(); },
  });
  const node = el("div", { class: "calendar-list" }, [body, addButton]);

  function blank() {
    return {
      id: "", label: "", descriptor: null, source: null,
      from_tick: null, until_tick: null, origin: null,
    };
  }

  function row(attachment) {
    const state = {
      label: attachment.label || "",
      id: attachment.id || "",
      from: attachment.from_tick == null ? "" : String(attachment.from_tick),
      until: attachment.until_tick == null ? "" : String(attachment.until_tick),
      // An id the writer has typed is theirs to keep; one we derived follows the
      // label, exactly as the book's own id follows its title.
      idTouched: Boolean(attachment.id) && attachment.id !== slugify(attachment.label || ""),
    };
    const field = calendarField({
      initial: attachment.descriptor,
      source: attachment.source,
      origin: attachment.origin,
      library,
      onCreateCalendar,
      onChange,
    });
    return { state, field };
  }

  // Ids are only *shown* when there is more than one calendar: with a single
  // reckoning nothing ever names it, so a required id box would be a question
  // with no consequence. They are still always *sent* — the switcher and every
  // `?calendar=` need a stable key.
  function idFor(entry, index) {
    if (entry.state.id.trim()) return entry.state.id.trim();
    return slugify(entry.state.label) || (index === 0 ? DEFAULT_ID : `calendar-${index + 1}`);
  }

  // `notify` is off for the first paint only, the same discipline the field
  // inside each row follows: constructing the list is not a change to report,
  // and the caller is still mid-assignment — `const list = calendarList({onChange})`
  // has not bound `list` yet, so an onChange that asks it anything throws
  // before the form is ever built.
  function rebuild(notify = true) {
    clear(body);
    rows.forEach((entry, index) => body.appendChild(render(entry, index)));
    addButton.hidden = rows.length >= MAX;
    if (notify) onChange();
  }

  function render(entry, index) {
    const many = rows.length > 1;
    const labelBox = el("input", {
      type: "text", value: entry.state.label, autocomplete: "off",
      placeholder: index === 0 ? "Imperial Reckoning" : "Elvish Count",
    });
    labelBox.addEventListener("input", () => {
      entry.state.label = labelBox.value;
      if (!entry.state.idTouched && idBox) idBox.value = slugify(labelBox.value);
      onChange();
    });

    const idBox = many ? el("input", {
      type: "text", value: idFor(entry, index), autocomplete: "off", placeholder: "imperial",
    }) : null;
    if (idBox) {
      idBox.addEventListener("input", () => {
        entry.state.idTouched = true;
        entry.state.id = idBox.value.trim();
        onChange();
      });
    }

    return el("div", { class: "calendar-row" }, [
      el("div", { class: "calendar-row-head" }, [
        field(many ? "Name" : "Name (optional)", labelBox, many
          ? "What the switcher calls this reckoning."
          : "Only shown once a book keeps more than one calendar."),
        idBox ? field("Id", idBox, "Used in links; derived from the name until you change it.") : null,
        many ? el("button", {
          class: "icon-btn sm", type: "button", text: "✕",
          title: "Remove this calendar. No scene moves — only its labels go.",
          onclick: () => { rows.splice(index, 1); rebuild(); },
        }) : null,
      ].filter(Boolean)),
      entry.field.node,
      many ? eraRow(entry) : null,
    ].filter(Boolean));
  }

  // Only offered alongside a second calendar, because that is the only time it
  // means anything: a lone reckoning that stops covering the book would leave
  // the writer with scenes that have no date at all.
  function eraRow(entry) {
    const from = tickInput(entry.state.from, "start of the story", (v) => {
      entry.state.from = v; onChange();
    });
    const until = tickInput(entry.state.until, "still kept", (v) => {
      entry.state.until = v; onChange();
    });
    return el("div", { class: "field-row era-row" }, [
      field("Kept from tick", from,
        "Where this reckoning starts counting. Its first year begins here."),
      field("Until tick", until,
        "When it stopped — a destroyed culture keeps no calendar. Scenes outside "
        + "this span read “before”/“after” rather than getting an invented date."),
    ]);
  }

  rebuild(false);

  return {
    node,
    // A row *names* a library calendar; it never carries the calendar itself.
    // The server reads the descriptor out of the library, so there is no second
    // copy in the browser to fall out of step. ``source.rev`` is the lever
    // described in ``_resolve_attachments``: present means "keep the copy this
    // book already holds", absent means "take it as it stands today".
    value: () => rows.map((entry, index) => ({
      id: idFor(entry, index),
      label: entry.state.label.trim(),
      source: entry.field.source(),
      from_tick: toTick(entry.state.from),
      until_tick: toTick(entry.state.until),
      origin: entry.field.origin(),
    })),
    problems: () => problems(rows, idFor),
  };
}

// Mirrors what the server enforces and goes no further — a browser that refuses
// what the API would accept is a worse bug than one that lets a 400 through.
function problems(rows, idFor) {
  const found = [];
  const seen = new Set();
  rows.forEach((entry, index) => {
    const id = idFor(entry, index);
    const where = entry.state.label.trim() || id;
    if (seen.has(id)) found.push(`Two calendars share the id “${id}”. Give one another name.`);
    seen.add(id);
    for (const problem of entry.field.problems()) found.push(`${where}: ${problem}`);
    const from = toTick(entry.state.from);
    const until = toTick(entry.state.until);
    for (const [value, raw, what] of [[from, entry.state.from, "Kept from"],
                                      [until, entry.state.until, "Until"]]) {
      if (raw.trim() && value === null) found.push(`${where}: “${what} tick” must be a whole number.`);
    }
    if (from !== null && until !== null && from >= until) {
      found.push(`${where}: it would end before it began.`);
    }
  });
  return found;
}

function toTick(raw) {
  if (!String(raw).trim()) return null;
  const value = Number(raw);
  return Number.isInteger(value) ? value : null;
}

function tickInput(value, placeholder, onInput) {
  const input = el("input", { type: "text", value, placeholder, autocomplete: "off" });
  input.setAttribute("inputmode", "numeric");
  input.addEventListener("input", () => onInput(input.value));
  return input;
}
