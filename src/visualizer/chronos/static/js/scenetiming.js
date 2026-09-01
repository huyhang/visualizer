// When a scene happens — the one part of the scene form with two ways to say
// the same thing.
//
// Ticks are what Chronos stores and every rule reads. Dates are what a writer
// thinks in, and are an *input spelling only*: the form resolves them to ticks
// before anything is saved, so nothing downstream ever learns which was typed.
//
// Two rules keep this honest. The date inputs are generated from the calendar's
// own units (see `datefields`), so any invented calendar — and Earth — works
// with no per-calendar code here. And no calendar arithmetic happens in the
// browser — the server resolves every date (api.resolveDates), because a client
// that disagreed with it about what "Day 12" means would be the worst possible
// bug in this feature.

import { api } from "./api.js";
import { calendarHint, dateUnits, plural, tickName } from "./calendars.js";
import { dateFields } from "./datefields.js";
import { clear, el } from "./dom.js";

const DEBOUNCE_MS = 250;

// -- reading the two kinds of input -------------------------------------------

function intOrNull(input) {
  const raw = input.value.trim();
  if (raw === "") return null;
  const n = Number(raw);
  return Number.isInteger(n) ? n : NaN;
}

// -- what the live hint says ---------------------------------------------------

function describeTicks(labelled, start, end, calendar) {
  const label = (tick) => (labelled.find((t) => t.tick === tick) || {}).label || String(tick);
  if (start === null) return `Ends ${label(end)} — but give a start too, or neither.`;
  if (end === null) return `Starts ${label(start)} — but give an end too, or neither.`;
  if (start > end) return `${label(start)} is after ${label(end)} — the start must come first.`;
  if (start === end) return `${label(start)} (a moment).`;
  return `${label(start)} → ${label(end)} (${end - start} ${plural(tickName(calendar))}).`;
}

// A resolved date says two things the writer wants: the period it landed on,
// and the ticks it became — the second because ticks are what the rest of
// Chronos will talk back to them in.
function describeDates(resolved, calendar) {
  const { start_tick: start, end_tick: end, ticks } = resolved;
  const label = (tick) => (ticks.find((t) => t.tick === tick) || {}).label || String(tick);
  const span = `${end - start} ${plural(tickName(calendar))}`;
  return `${label(start)} → ${label(end)} (${span}) — ticks ${start} → ${end}.`;
}

// Silent unless the book keeps more than one calendar: a single reckoning is
// already the line above, and repeating it would be noise.
function showReadings(list, ticks, at) {
  const entry = ticks.find((t) => t.tick === at) || ticks[0];
  const readings = (entry && entry.readings) || [];
  clear(list);
  list.hidden = readings.length < 2;
  if (list.hidden) return;
  for (const reading of readings) {
    list.appendChild(el("li", { text: `${reading.name}: ${reading.label}` }));
  }
}

// Whether asking the server for a label would tell the writer anything: with no
// calendar the label *is* the number, so the round trip would be noise.
export function labelsAreUseful(calendar) {
  if (!calendar || calendar.kind === "identity") return false;
  // Earth carries no cycles — its months are not a thing this book declares —
  // so the shape test below would say its labels are worthless. They are the
  // whole point of it.
  return calendar.kind === "gregorian" || (calendar.cycles || []).length > 0;
}

// -- the section ---------------------------------------------------------------

// `calendars` is the book's attachments, `calendarId` which of them to start in
// (null for the primary). A writer may switch between them here rather than
// only on the page around the form: a scene set in elvish lands is more
// naturally dated in the Elvish Count, whatever the book's primary reckoning is.
// The choice lasts as long as the form — it decides how the timeframe is
// *entered*, and what gets stored is the tick either way.
//
// Returns { node, timeframe() }, where timeframe() is { body, calendar } or
// { error }. `calendar` must reach the save: the writer was shown what their
// date resolves to through it, and any other reckoning gives a different tick.
export function sceneTiming(book, {
  calendars = [], calendarId = null, event = null,
} = {}) {
  const attached = calendars.length ? calendars : [];
  const chosenAt = (id) => attached.find((c) => c.id === id) || attached[0] || null;
  let current = chosenAt(calendarId);
  let calendar = current ? current.descriptor : null;
  let units = dateUnits(calendar);
  const scheduled = Boolean(event && event.start_tick != null);
  // The last timeframe we know in ticks, so switching calendars can re-express
  // the same moment rather than making the writer type it again.
  let lastTicks = scheduled ? { start: event.start_tick, end: event.end_tick } : null;

  const startTick = el("input", { type: "text", inputmode: "numeric", placeholder: "e.g. 240",
    value: scheduled ? String(event.start_tick) : "" });
  const endTick = el("input", { type: "text", inputmode: "numeric", placeholder: "e.g. 264",
    value: scheduled ? String(event.end_tick) : "" });
  const tickRow = el("div", { class: "field-row" }, [
    labelled("Starts at (tick)", startTick),
    labelled("Ends at (tick)", endTick),
  ]);

  // Rebuilt whenever the calendar changes: a different reckoning means a
  // different set of units, so the boxes themselves are what has to change.
  const dateRow = el("div", { class: "field-row" });
  let startDate = null;
  let endDate = null;

  const hint = el("p", { class: "field-hint tick-preview muted" });
  const readings = el("ul", { class: "field-hint tick-readings muted", hidden: "" });
  // The plain-language reading of whichever calendar is selected, so switching
  // explains the new one rather than leaving the first one's sentence behind.
  const reading = el("p", { class: "field-hint muted" });

  // Dates when the book has a calendar to write them in; ticks otherwise. The
  // toggle stays available either way a book *can* be dated, because a tick is
  // still the only way to paste an exact time — or to place a scene outside the
  // years a reckoning was kept.
  let mode = units.length ? "date" : "tick";

  const modes = units.length ? modeToggle(switchMode) : null;
  // Set while the form is moving a timeframe between spellings, so a fallback
  // to Tick mode raised *during* a carry does not start a second one on top of
  // the first -- which would read the half-filled boxes it is in the middle of
  // writing and wipe the timeframe it was preserving.
  let carrying = false;

  // Only offered when there is a choice to make; one reckoning is not a menu.
  const picker = attached.length > 1 ? calendarPicker(attached, current, switchTo) : null;

  let timer = null;
  let seq = 0;
  const schedule = () => { clearTimeout(timer); timer = setTimeout(refresh, DEBOUNCE_MS); };
  for (const input of [startTick, endTick]) input.addEventListener("input", schedule);

  function applyMode() {
    tickRow.hidden = mode !== "tick";
    dateRow.hidden = mode !== "date";
  }

  // Ticks and dates are two spellings of one timeframe, so the toggle has to
  // carry it across. Without this the hidden spelling keeps whatever it held
  // when the form opened, and saving from the other side silently discards the
  // edit the writer just made -- the same value being visibly wrong in a box
  // they cannot see.
  async function switchMode(picked) {
    const leaving = mode;
    mode = picked;
    applyMode();
    if (!carrying && leaving !== picked) {
      carrying = true;
      try {
        if (picked === "tick") await carryDatesToTicks();
        else await carryTicksToDates();
      } finally {
        carrying = false;
      }
    }
    return refresh();
  }

  async function carryDatesToTicks() {
    const asked = dateBody();
    if (asked.error) return;  // nothing trustworthy to carry; leave the ticks be
    if (!asked.body) return clearTicks();
    try {
      const r = await api.resolveDates(book, asked.body, { calendar: chosenId() });
      startTick.value = String(r.start_tick);
      endTick.value = String(r.end_tick);
      lastTicks = { start: r.start_tick, end: r.end_tick };
    } catch (e) { /* the hint below will say what went wrong */ }
  }

  async function carryTicksToDates() {
    const asked = tickBody();
    if (asked.error) return;
    const { start_tick: start, end_tick: end } = asked.body;
    if (start === null) return clearDates();
    lastTicks = { start, end };
    await showTicksAsDate(lastTicks);
  }

  function clearTicks() {
    startTick.value = "";
    endTick.value = "";
    lastTicks = null;
  }

  function clearDates() {
    if (startDate) startDate.fill(null);
    if (endDate) endDate.fill(null);
    lastTicks = null;
  }

  function buildDateInputs() {
    clear(dateRow);
    startDate = endDate = null;
    if (!units.length) return;
    startDate = dateFields(units);
    endDate = dateFields(units);
    for (const input of [...startDate.controls, ...endDate.controls]) {
      input.addEventListener("input", schedule);
    }
    dateRow.appendChild(labelled("Starts", startDate.node));
    dateRow.appendChild(labelled("Ends", endDate.node));
  }

  // Change which reckoning the writer is typing in, carrying the timeframe
  // across. Nothing about the scene moves: the ticks are the same ticks, said
  // in another calendar's words.
  async function switchTo(attachment) {
    current = attachment;
    calendar = attachment.descriptor;
    units = dateUnits(calendar);
    buildDateInputs();
    if (!units.length && mode === "date" && modes) modes.choose("tick");
    applyMode();
    reading.textContent = calendarHint(calendar);
    if (lastTicks) await showTicksAsDate(lastTicks);
    return refresh();
  }

  function say(message) {
    hint.textContent = message;
    readings.hidden = true;
  }

  // Latest-wins: a slow answer for an older keystroke must not overwrite a
  // newer one, which on a debounced field is otherwise easy to hit.
  async function refresh() {
    const mine = ++seq;
    const asked = mode === "date" ? previewDates() : previewTicks();
    try {
      const said = await asked;
      if (mine === seq && said) hint.textContent = said;
    } catch (err) {
      if (mine === seq) say(err.message || "");
    }
  }

  async function previewTicks() {
    if (!labelsAreUseful(calendar)) return null;
    const start = intOrNull(startTick);
    const end = intOrNull(endTick);
    if (Number.isNaN(start) || Number.isNaN(end)) return "Whole numbers only.";
    if (start === null && end === null) return unscheduledHint();
    const wanted = [start, end].filter((t) => t !== null);
    const { ticks } = await api.formatTicks(book, wanted, { calendar: chosenId() });
    showReadings(readings, ticks, start);
    if (start !== null && end !== null) lastTicks = { start, end };
    return describeTicks(ticks, start, end, calendar);
  }

  async function previewDates() {
    const asked = dateBody();
    if (asked.error) return asked.error;
    if (!asked.body) return unscheduledHint();
    const resolved = await api.resolveDates(book, asked.body, { calendar: chosenId() });
    showReadings(readings, resolved.ticks, resolved.start_tick);
    lastTicks = { start: resolved.start_tick, end: resolved.end_tick };
    return describeDates(resolved, calendar);
  }

  function unscheduledHint() {
    readings.hidden = true;
    return "No timing yet — you can place this scene later.";
  }

  // The date pair as the API takes it. Null body means "no timing", which is a
  // legitimate answer (an unscheduled scene), not a failure.
  function dateBody() {
    const start = startDate.value();
    const end = endDate.value();
    if (start.error || end.error) return { error: start.error || end.error };
    const bothEmpty = startDate.empty() && endDate.empty();
    if (bothEmpty) return { body: null };
    if (startDate.empty() || endDate.empty()) {
      return { error: "Give both dates, or neither — a half-known timeframe is not supported." };
    }
    return { body: { start_date: start.date, end_date: end.date } };
  }

  function tickBody() {
    const start = intOrNull(startTick);
    const end = intOrNull(endTick);
    if (Number.isNaN(start) || Number.isNaN(end)) return { error: "Ticks must be whole numbers." };
    if ((start === null) !== (end === null)) {
      return { error: "Give both ticks, or neither — a half-known timeframe is not supported." };
    }
    if (start !== null && start > end) return { error: "The start must not be after the end." };
    return { body: { start_tick: start, end_tick: end } };
  }

  // Show a known timeframe in the current reckoning's date boxes — how an
  // existing scene opens, and how a timeframe survives a change of calendar.
  //
  // A reckoning that was not being kept then has no date for these ticks, so
  // rather than leaving blank boxes the form drops to Tick mode holding the
  // ticks themselves. Blank boxes would be worse than useless here: saving them
  // would unschedule the scene, which is not what switching a calendar means.
  async function showTicksAsDate({ start, end }) {
    startTick.value = String(start);
    endTick.value = String(end);
    // A zero-length span names no period, so no date can express it. It can only
    // arrive by typing ticks, and it stays in ticks.
    if (!units.length || end <= start) return dropToTicks();
    try {
      // The end tick is *exclusive*, but a date box says the period the scene
      // covers — so it shows the last tick inside the scene, not the first one
      // after it. Filling it from `end` itself resolves one unit later, which
      // would grow a scene by a tick every time a writer opened it and saved
      // without touching anything.
      const inside = end - 1;
      const { ticks } = await api.formatTicks(book, [start, inside], { calendar: chosenId() });
      const at = (tick) => (ticks.find((t) => t.tick === tick) || {}).components || null;
      const from = at(start);
      const to = at(inside);
      if (from && to) {
        startDate.fill(from);
        endDate.fill(to);
        return true;
      }
    } catch (e) { /* the hint will say what went wrong */ }
    return dropToTicks();
  }

  function dropToTicks() {
    if (!modes) return false;
    // Flipped *for* the writer rather than *by* them, and the tick boxes are
    // already correct -- so this must not trigger a carry back the other way.
    const was = carrying;
    carrying = true;
    try {
      modes.choose("tick");
    } finally {
      carrying = was;
    }
    return false;
  }

  function chosenId() {
    return current ? current.id : null;
  }

  buildDateInputs();
  applyMode();
  reading.textContent = calendarHint(calendar);
  if (lastTicks) showTicksAsDate(lastTicks).then(refresh);
  else refresh();

  return {
    node: el("div", { class: "timing" }, [
      el("div", { class: "timing-controls" }, [
        modes ? modes.node : null,
        picker ? picker.node : null,
      ]),
      tickRow,
      dateRow,
      hint,
      readings,
      reading,
    ]),
    // What to send, and which reckoning to send it through. The server applies
    // these same rules again — this only spares the writer a round trip to hear
    // them.
    timeframe: () => {
      const result = mode === "date" ? withNulls(dateBody()) : tickBody();
      if (result.error) return result;
      // Ticks mean the same thing in every calendar, but the response is
      // presented through this one, so it rides along either way.
      return { body: result.body, calendar: chosenId() };
    },
  };
}

// An unscheduled scene has to *say* it is unscheduled: a PUT is a full replace,
// so omitting the fields would leave a retimed scene wearing its old ticks.
function withNulls(result) {
  if (result.error) return result;
  return { body: result.body || { start_tick: null, end_tick: null } };
}

// Which of the book's reckonings the writer is typing in. A plain select: the
// list is short, the choice is not a mode, and it needs to say the calendar's
// name rather than abbreviate it.
function calendarPicker(attached, current, onChange) {
  const select = el("select", { class: "calendar-choice", title: "Which calendar to write dates in" },
    attached.map((c) => el("option", { value: c.id, text: c.label || c.id })));
  select.value = current ? current.id : attached[0].id;
  select.addEventListener("change", () => {
    const picked = attached.find((c) => c.id === select.value);
    if (picked) onChange(picked);
  });
  return {
    node: el("label", { class: "calendar-choice-field" }, [
      el("span", { class: "muted", text: "Dates in" }),
      select,
    ]),
  };
}

function labelled(label, control) {
  return el("div", { class: "field" }, [
    el("label", { class: "field-label", text: label }),
    control,
  ]);
}

function modeToggle(onChange) {
  const options = [["date", "Date"], ["tick", "Tick"]];
  const inputs = new Map();
  const name = `timing-mode-${Math.random().toString(36).slice(2)}`;
  const node = el("div", { class: "timing-mode", role: "radiogroup" },
    options.map(([value, text]) => {
      const input = el("input", { type: "radio", name, value });
      if (value === "date") input.checked = true;
      input.addEventListener("change", () => { if (input.checked) onChange(value); });
      inputs.set(value, input);
      return el("label", { class: "timing-mode-option" }, [input, el("span", { text })]);
    }));
  return {
    node,
    choose: (value) => {
      const input = inputs.get(value);
      if (!input || input.checked) return;
      input.checked = true;
      onChange(value);
    },
  };
}
