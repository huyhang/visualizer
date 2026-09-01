// The control that decides what a tick means in a book.
//
// Its contract is `source() -> {owner, calendar, rev} | null` and
// `problems() -> string[]`. Note what is *not* in it: a descriptor. The library
// is where calendars are authored; a book names one, and the server copies the
// content in. So there is no second copy of a calendar in the browser to fall
// out of step, and no way for this form to invent one.
//
// The copy still matters, and `rev` is how it is held: a book keeps the
// calendar it took, and one writer's later edit can never re-date another
// writer's story until that writer accepts it here.
//
// Two exports, because two callers need different things:
//   - `inlineCalendarEditor` — the cycles editor. Used by the *library* form,
//     which is the one place a calendar is actually written.
//   - `calendarField` — a book's choice between "no calendar" and one from the
//     library. It never edits cycles; it picks.
//
// Redraw discipline (the library editor below): typing mutates the draft and
// refreshes only the hint in place, so the caret stays put. Cycle rows are
// rebuilt only when their *number* changes.

import { clear, el } from "./dom.js";
import {
  GREGORIAN_TICK_UNITS, PRESETS, calendarHint, calendarProblems, dateUnits,
  descriptorFrom, draftFrom, emptyCycle,
} from "./calendars.js";
import { dateFields } from "./datefields.js";

// -- the bare editor ----------------------------------------------------------

export function inlineCalendarEditor({ initial = null, onChange = () => {} } = {}) {
  const state = { draft: draftFrom(initial) };
  const body = el("div", { class: "calendar-body" });

  function rebuild(focusCycle = null, notify = true) {
    clear(body);
    body.appendChild(calendarKind(state, { rebuild }));
    body.appendChild(state.draft.kind === "gregorian"
      ? gregorianEditor(state, { refresh })
      : inlineEditor(state, { rebuild, refresh, onChange }));
    if (focusCycle !== null) {
      const input = body.querySelectorAll(".cycle-row input")[focusCycle * 2];
      if (input) input.focus();
    }
    if (notify) onChange();
  }

  // The live feedback that must survive a keystroke without a rebuild.
  function refresh() {
    const hint = body.querySelector(".calendar-reading");
    if (hint) hint.textContent = calendarHint(descriptorFrom(state.draft));
    onChange();
  }

  rebuild(null, false);

  return {
    node: body,
    value: () => descriptorFrom(state.draft),
    problems: () => calendarProblems(state.draft),
  };
}

// -- the mode chooser ---------------------------------------------------------

// Each mode owns how it produces a descriptor, what it renders, and what is
// wrong with it. The list is the extension point, and the library entry is what
// it was left open for.
//
// There are two, because a book has two things it can say about time: it uses
// one of your calendars, or it uses none and shows plain ticks. It cannot
// describe a calendar of its own — the library is where calendars are authored,
// and the server refuses a book body that carries a descriptor.
const MODES = [
  {
    key: "none",
    label: "No calendar",
    calendar: () => null,
    problems: () => [],
    body: () => el("p", { class: "field-hint muted", text:
      "Scenes are placed at whole-number ticks and read back as those numbers. "
      + "Pick a scale — hours, days, chapters — and stay consistent." }),
  },
  {
    key: "library",
    label: "From your library",
    calendar: (state) => state.picked,
    problems: (state) => (state.picked ? [] : ["Choose a calendar from your library."]),
    body: (state, deps) => libraryPicker(state, deps),
  },
];

// `library` is the writer's calendars (from `api.listCalendars`), or [] if they
// have none — in which case the mode is offered but says so plainly rather than
// presenting an empty select.
export function calendarField({
  initial = null, source = null, origin = null, library = [],
  onCreateCalendar = null, onChange = () => {},
} = {}) {
  const state = {
    mode: source ? "library" : "none",
    picked: pickedFrom(library, source, initial),
    // What this book already holds, so an ordinary save can say "keep mine".
    held: source || null,
    // Flipped only by the update offer below -- the one deliberate act that
    // lets a library change into a book.
    tookUpdate: false,
    // Where this book sits on Earth's timeline, for a Gregorian calendar. Held
    // as the boxes the writer typed rather than as the string they compose to,
    // so a half-finished date survives a rebuild.
    origin: null,
    originText: origin || "",
  };

  const body = el("div", { class: "calendar-body" });
  // Naming the question the tabs answer. Without it they read as three loose
  // buttons, and the middle one gets mistaken for a control that *adds* a
  // calendar rather than one that says how this reckoning is defined. Same
  // words the library form uses over the same editor.
  const node = el("div", { class: "calendar-field" }, [
    el("p", { class: "field-label", text: "How it counts" }),
    modeTabs(),
    body,
  ]);

  const current = () => MODES.find((m) => m.key === state.mode);

  function modeTabs() {
    const tabs = el("div", { class: "tabs" });
    for (const mode of MODES) {
      tabs.appendChild(el("button", {
        class: `tab${mode.key === state.mode ? " active" : ""}`,
        type: "button", text: mode.label, dataset: { mode: mode.key },
        onclick: () => {
          if (state.mode === mode.key) return;
          state.mode = mode.key;
          for (const tab of tabs.children) tab.classList.toggle("active", tab.dataset.mode === mode.key);
          rebuild();
        },
      }));
    }
    return tabs;
  }

  // `notify` is off for the first paint only: constructing a field is not a
  // change to report, and the caller is still mid-assignment — it cannot answer
  // a question about a field it does not yet hold a reference to.
  function rebuild(focusCycle = null, notify = true) {
    clear(body);
    body.appendChild(current().body(state, { rebuild, onChange, library, onCreateCalendar }));
    if (focusCycle !== null) {
      const input = body.querySelectorAll(".cycle-row input")[focusCycle * 2];
      if (input) input.focus();
    }
    if (notify) onChange();
  }

  rebuild(null, false);

  const chosen = () => current().calendar(state);

  return {
    node,
    // What the caller sends: the library calendar this attachment names, or
    // null for plain ticks. The *descriptor* is deliberately absent — the
    // server reads it out of the library, so the browser never carries content
    // it could get out of step with.
    source: () => {
      const picked = chosen();
      if (!picked) return null;
      // Send the held revision only when this is still the calendar the book
      // already had and the writer has not taken the update. Anything else --
      // a different calendar, or the offer accepted -- is a fresh attach, and
      // omitting the revision is how that asks for the current entry.
      const unchanged = state.held
        && state.held.owner === picked.owner && state.held.calendar === picked.id;
      const rev = unchanged && !state.tookUpdate ? state.held.rev : null;
      return { owner: picked.owner, calendar: picked.id, rev };
    },
    // For display only: what this calendar currently reads as.
    descriptor: () => (chosen() ? chosen().descriptor : null),
    // Which Earth moment this book's tick 0 was, or null for any calendar that
    // does not sit on Earth's timeline.
    origin: () => (isEarth(state) ? state.originText || null : null),
    problems: () => [...current().problems(state), ...originProblems(state)],
  };
}

// What a library-sourced attachment *is*, as loaded: the descriptor the book
// already holds, pinned at the revision it was taken from.
//
// Emphatically **not** the library entry as it stands today. Reading today's
// descriptor here would mean that merely opening this form and pressing Save
// applied any drift — silently, with no preview and nothing on screen to say a
// book's dates had just been rewritten. That is the exact failure copying the
// descriptor into the book exists to prevent, and it would arrive through the
// one door every writer uses.
//
// The library row is still carried, for its name and for noticing that a newer
// revision exists. Taking that revision is a separate, deliberate click.
function pickedFrom(library, source, initial) {
  if (!source) return null;
  const entry = (library || []).find(
    (c) => c.owner === source.owner && c.id === source.calendar,
  );
  const qualified = `${source.owner}/${source.calendar}`;
  if (!entry) {
    // Deleted, or never shared with this reader. The book keeps working — its
    // calendar is its own bytes — and the link is kept so the form can say why
    // no updates are on offer, rather than looking hand-written.
    return {
      owner: source.owner, id: source.calendar, rev: source.rev,
      qualified_id: qualified, name: qualified,
      descriptor: initial, unreachable: true,
    };
  }
  return { ...entry, rev: source.rev, descriptor: initial };
}

// -- the library picker -------------------------------------------------------

function libraryPicker(state, deps) {
  const library = deps.library || [];
  const picked = state.picked;
  const options = [...library];
  // A calendar that has been deleted, or was never shared with this reader, is
  // still what this book uses. It has to stay in the list or the select would
  // silently show something else as chosen.
  if (picked && picked.unreachable) options.unshift(picked);

  const choose = el("select", {}, [
    el("option", { value: "", text: "— choose a calendar —" }),
    ...options.map((c) => el("option", { value: c.qualified_id, text: optionLabel(c, options) })),
  ]);
  choose.value = picked ? picked.qualified_id : "";
  choose.addEventListener("change", () => {
    state.picked = library.find((c) => c.qualified_id === choose.value) || null;
    deps.rebuild();
  });

  // The way out of an empty library, and the reason a writer never has to leave
  // the book form to get one. It creates the calendar *in the library* — the
  // book still only ever names it.
  const create = deps.onCreateCalendar ? el("button", {
    class: "btn secondary sm", type: "button", text: "＋ New calendar",
    onclick: async () => {
      const made = await deps.onCreateCalendar();
      if (!made) return;
      state.picked = made;
      deps.rebuild();
    },
  }) : null;

  return el("div", {}, [
    library.length ? choose : el("p", { class: "field-hint muted", text:
      "Your library is empty. Build one here and it will be offered to every "
      + "other book you write." }),
    create,
    picked ? el("p", { class: "field-hint muted calendar-reading",
      text: calendarHint(picked.descriptor) }) : null,
    gregorianOrigin(state, deps),
    updateOffer(state, library, deps),
    el("p", { class: "field-hint muted", text: picked && picked.unreachable
      ? `Copied from ${picked.qualified_id}, which you can no longer see — deleted, `
        + "or no longer shared with you. This book keeps its own copy, so its "
        + "dates are unaffected; there is just nothing left to offer updates from."
      : "The calendar is copied into this book when you save. Editing it in your "
        + "library later will not change this book until you take the change "
        + "here — and a book someone shares with you keeps working even if they "
        + "never share the calendar." }),
  ].filter(Boolean));
}

// -- where this book sits on Earth's timeline ---------------------------------
//
// The one thing a book says about a calendar's *content*, and only ever about
// an Earth one. It is asked here rather than in the library because it is this
// story's alignment: two books may share the same Earth calendar and sit
// centuries apart. Everything else on this form still only names a calendar.

// What the API stores: a date, and a time with a fixed offset when ticks are
// finer than a day. Written by `composeOrigin`, never typed directly — which is
// why a year before 1 can be stored as the plain count `-0043` without anyone
// having to know that is how 44 BCE is spelled.
const ORIGIN = /^(-?\d+)-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(.*))?$/;
const OFFSET = /^(Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;

function isEarth(state) {
  const picked = state.mode === "library" ? state.picked : null;
  return Boolean(picked && picked.descriptor && picked.descriptor.kind === "gregorian");
}

function gregorianOrigin(state, deps) {
  state.origin = null;
  if (!isEarth(state)) return null;
  const { tick_unit: unit } = state.picked.descriptor;
  const units = dateUnits(state.picked.descriptor);
  const held = splitOrigin(state.originText);

  const fields = dateFields(units);
  fields.fill(held.components);
  const offset = unit === "day" ? null : textInput(held.offset, "Z", record);

  function record() {
    state.originText = composeOrigin(fields, units, offset, unit);
    deps.onChange();
  }
  for (const control of fields.controls) control.addEventListener("input", record);
  state.origin = { fields, offset };

  return el("div", { class: "field gregorian-origin" }, [
    el("label", { class: "field-label", text: "This book's tick 0 fell on" }),
    el("p", { class: "field-hint muted", text:
      "Where your story meets Earth's timeline. Asked here rather than in the "
      + "library, because another book may use the same calendar centuries apart." }),
    el("div", { class: "field-row" }, [
      fields.node,
      offset ? labelled("UTC offset", offset,
        "Z, or a fixed offset like -08:00. Daylight saving is not applied.") : null,
    ].filter(Boolean)),
  ]);
}

// The boxes as the API spells them, or "" while any of them is still blank. An
// origin is the one date that may not name a period: a half-filled one would
// quietly become the first of January, which is not what was typed.
function composeOrigin(fields, units, offset, unit) {
  const { date, error } = fields.value();
  if (error || units.some(({ name }) => date[name] === undefined)) return "";
  const pad = (n, width) => String(Math.abs(n)).padStart(width, "0");
  const sign = date.year < 0 ? "-" : "";
  const day = `${sign}${pad(date.year, 4)}-${pad(date.month, 2)}-${pad(date.day, 2)}`;
  if (unit === "day") return day;
  const clock = `${pad(date.hour, 2)}:${pad(date.minute || 0, 2)}`;
  return `${day}T${clock}${(offset && offset.value.trim()) || "Z"}`;
}

function splitOrigin(text) {
  const match = ORIGIN.exec(String(text || ""));
  if (!match) return { components: null, offset: "Z" };
  const [, year, month, day, hour, minute, offset] = match;
  const components = { year: Number(year), month: Number(month), day: Number(day) };
  if (hour !== undefined) {
    components.hour = Number(hour);
    components.minute = Number(minute);
  }
  return { components, offset: offset || "Z" };
}

// Mirrors the server and goes no further, the same discipline as
// `calendarProblems`: a browser that refuses what the API would accept is a
// worse bug than one that lets a 400 through.
function originProblems(state) {
  if (!isEarth(state)) return [];
  const live = state.origin;
  if (live) {
    const { error } = live.fields.value();
    if (error) return [error];
    if (live.offset && !OFFSET.test(live.offset.value.trim())) {
      return ["Use Z for UTC, or a fixed offset like -08:00."];
    }
  }
  if (!state.originText) {
    return ["Say which Earth date this book's tick 0 fell on."];
  }
  return [];
}

// "The library version has moved on — take it?" Explicit and previewable,
// which is the whole reason an attachment records the revision it holds.
// Nothing happens until this is clicked, and clicking it changes only what this
// book will be saved with.
//
// Taking an update is one-way: library calendars keep no history, so there is
// no revision to go back to once the book stops holding it.
function updateOffer(state, library, deps) {
  const picked = state.picked;
  if (!picked || picked.unreachable || state.tookUpdate) return null;
  const latest = library.find((c) => c.qualified_id === picked.qualified_id);
  if (!latest || !(latest.rev > picked.rev)) return null;

  return el("div", { class: "update-offer" }, [
    el("p", { class: "field-hint", text:
      `${picked.qualified_id} has changed since this book copied it `
      + `(your copy: revision ${picked.rev}; the library: revision ${latest.rev}).` }),
    el("p", { class: "field-hint muted", text: `It now reads — ${calendarHint(latest.descriptor)}` }),
    el("button", {
      class: "btn secondary sm", type: "button", text: "Use the newer version",
      onclick: () => {
        // Both, together: the descriptor shown, and the flag that stops the
        // save replaying the old revision back at the server.
        state.tookUpdate = true;
        state.picked = { ...latest };
        deps.rebuild();
      },
    }),
  ]);
}

// Own calendars read bare; someone else's are owner-qualified, which is also
// what keeps two people's "Imperial Reckoning" apart in one list.
function optionLabel(calendar, library) {
  const clashes = library.filter((c) => c.name === calendar.name).length > 1;
  return clashes ? `${calendar.name} (${calendar.qualified_id})` : calendar.name;
}

// -- the inline editor --------------------------------------------------------

// Which of the two things a calendar can be. Switching replaces the draft
// outright rather than merging: a half-kept fantasy cycle list riding along
// inside an Earth calendar is exactly the kind of leftover that gets saved by
// accident later.
function calendarKind(state, deps) {
  const choose = el("select", {}, [
    el("option", { value: "mixed_radix", text: "Invented — fixed cycles" }),
    el("option", { value: "gregorian", text: "Earth — Gregorian months" }),
  ]);
  choose.value = state.draft.kind === "gregorian" ? "gregorian" : "mixed_radix";
  choose.addEventListener("change", () => {
    state.draft = choose.value === "gregorian"
      ? { kind: "gregorian", tickUnit: "day" }
      : PRESETS[0].draft();
    deps.rebuild();
  });
  return labelled("What kind of calendar", choose,
    "Earth's months are 28, 29, 30 or 31 days and are not yours to set.");
}

// Everything an Earth calendar gets to choose. Which Earth date a book's tick 0
// was is asked for on the *book* — see `gregorianOrigin` — because it is that
// story's alignment, not a property of the calendar being written here.
function gregorianEditor(state, deps) {
  const choose = el("select", {}, GREGORIAN_TICK_UNITS.map((value) =>
    el("option", { value, text: capitalize(value) })));
  choose.value = state.draft.tickUnit;
  choose.addEventListener("change", () => {
    state.draft.tickUnit = choose.value;
    deps.refresh();
  });
  return el("div", {}, [
    labelled("One tick is a…", choose,
      "The smallest unit your story counts in. Fixed, even though the months are not."),
    el("p", { class: "field-hint muted calendar-reading",
      text: calendarHint(descriptorFrom(state.draft)) }),
  ]);
}

function inlineEditor(state, deps) {
  const { draft } = state;

  const baseUnit = textInput(draft.baseUnit, "hour", (v) => { draft.baseUnit = v; deps.refresh(); });
  const epoch = textInput(draft.epochLabel, "AF", (v) => { draft.epochLabel = v; deps.refresh(); });

  const rows = el("div", { class: "cycle-rows" }, draft.cycles.map((cycle, index) =>
    cycleRow(cycle, index, draft, deps)));

  return el("div", {}, [
    el("div", { class: "field-row" }, [
      labelled("One tick is a…", baseUnit, "The smallest unit your story counts in."),
      labelled("Era (optional)", epoch, "Appended to every label, e.g. “AF”."),
    ]),
    el("div", { class: "field" }, [
      el("label", { class: "field-label", text: "Cycles" }),
      el("p", { class: "field-hint muted", text:
        "Smallest first: each one counts how many of the unit below it make one of these." }),
      rows,
      el("button", {
        class: "btn secondary sm", type: "button", text: "+ Add a cycle",
        onclick: () => { draft.cycles.push(emptyCycle()); deps.rebuild(draft.cycles.length - 1); },
      }),
    ]),
    el("div", { class: "field" }, [
      el("label", { class: "field-label", text: "Start from" }),
      presetButtons(state, deps),
    ]),
    el("p", { class: "field-hint muted calendar-reading",
      text: calendarHint(descriptorFrom(draft)) }),
  ]);
}

function cycleRow(cycle, index, draft, deps) {
  const name = textInput(cycle.name, "day", (v) => { cycle.name = v; deps.refresh(); });
  const size = textInput(cycle.size, "24", (v) => { cycle.size = v; deps.refresh(); });
  size.setAttribute("inputmode", "numeric");
  return el("div", { class: "cycle-row" }, [
    el("span", { class: "cycle-index muted", text: `${index + 1}.` }),
    name,
    el("span", { class: "cycle-of muted", text: "made of" }),
    size,
    el("button", {
      class: "icon-btn sm", type: "button", text: "✕", title: "Remove this cycle",
      onclick: () => { draft.cycles.splice(index, 1); deps.rebuild(); },
    }),
  ]);
}

function presetButtons(state, deps) {
  return el("div", { class: "inline-controls" }, PRESETS.map((preset) => el("button", {
    class: "btn secondary sm", type: "button", text: preset.label,
    onclick: () => { state.draft = preset.draft(); deps.rebuild(); },
  })));
}

// -- small pieces -------------------------------------------------------------

const capitalize = (word) => String(word).charAt(0).toUpperCase() + String(word).slice(1);

function textInput(value, placeholder, onInput) {
  const input = el("input", { type: "text", value, placeholder, autocomplete: "off" });
  input.addEventListener("input", () => onInput(input.value));
  return input;
}

function labelled(label, control, hint) {
  return el("div", { class: "field" }, [
    el("label", { class: "field-label", text: label }),
    control,
    hint ? el("p", { class: "field-hint muted", text: hint }) : null,
  ]);
}
