// The control that decides what a tick means in a new book.
//
// Its whole contract with a caller is `value() -> descriptor | null` and
// `problems() -> string[]`. Nothing outside this module learns *where* the
// descriptor came from, which is the point: today a book's calendar is either
// absent or typed in here, and a shared calendar library is the planned next
// step. Adding it is one more entry in MODES plus the body it renders — no
// caller changes, because a picked calendar and a typed one are the same
// descriptor by then.
//
// Redraw discipline: typing mutates the draft and refreshes only the hint and
// the problem list (in place, so the caret stays put). The rows are rebuilt only
// when their *number* changes.

import { clear, el } from "./dom.js";
import {
  PRESETS, calendarHint, calendarProblems, descriptorFrom, draftFrom, emptyCycle,
} from "./calendars.js";

// Each mode owns how it produces a descriptor, what it renders, and what is
// wrong with it. The list is the extension point.
const MODES = [
  {
    key: "none",
    label: "Plain numbers",
    descriptor: () => null,
    problems: () => [],
    body: () => el("p", { class: "field-hint muted", text:
      "Scenes are placed at whole-number ticks and read back as those numbers. "
      + "Pick a scale — hours, days, chapters — and stay consistent." }),
  },
  {
    key: "inline",
    label: "A calendar",
    descriptor: (state) => descriptorFrom(state.draft),
    problems: (state) => calendarProblems(state.draft),
    body: (state, deps) => inlineEditor(state, deps),
  },
];

export function calendarField({ initial = null, onChange = () => {} } = {}) {
  const state = {
    mode: initial ? "inline" : "none",
    // Kept even while "Plain numbers" is selected, so toggling back and forth
    // does not throw away a calendar the writer already typed.
    draft: draftFrom(initial),
  };

  const body = el("div", { class: "calendar-body" });
  const node = el("div", { class: "calendar-field" }, [modeTabs(), body]);

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
    body.appendChild(current().body(state, { rebuild, refresh, onChange }));
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
    node,
    value: () => current().descriptor(state),
    problems: () => current().problems(state),
  };
}

// -- the inline editor --------------------------------------------------------

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
