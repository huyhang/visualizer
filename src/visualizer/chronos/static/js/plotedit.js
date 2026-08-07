// The plotline editor: write a new thread, or change an existing one's name,
// goals, continuation and — the point of the exercise — the order of its scenes.
//
// Three decisions shape this module:
//
// * **Edit mode, saved explicitly.** Dragging is a draft; one PUT commits it,
//   carrying If-Match so a save that would clobber someone else's edit is
//   refused rather than winning silently. Cancel costs nothing.
// * **The server judges the draft.** After every change the candidate is sent to
//   the preview endpoint, which returns it presented exactly as saving it would
//   — resolved path, per-scene findings, status. So conflicts appear *while you
//   drag*, and no story rule is reimplemented here.
// * **Only your own scenes move.** A thread that continues into another inherits
//   that thread's scenes; they are shown, locked, because they are stored
//   elsewhere and an edit has to go there.
//
// It opens as a modal over whatever you were looking at, rather than as its own
// route: editing a thread is a detour from reading it, and coming back should
// put you exactly where you were -- same table page, same filter, same scroll.

import { api } from "./api.js";
import { eventTimeframe } from "./cards.js";
import { clear, el, toast } from "./dom.js";
import { findingList, markerClass, problemBanner, verdictNotes } from "./findings.js";
import { confirmModal, modal, suggestBox } from "./picker.js";
import { loadScope, sceneForm } from "./sceneform.js";

const PREVIEW_DEBOUNCE_MS = 250;

// -- pure-ish list helpers ---------------------------------------------------

export function move(list, from, to) {
  const out = list.slice();
  const [item] = out.splice(from, 1);
  out.splice(to, 0, item);
  return out;
}

// Scheduled scenes by start tick, undated ones left at the end in their current
// order. Offered as a one-click fix for a thread whose scenes are simply typed
// in the wrong order.
export function byTime(ids, rowFor) {
  const dated = ids.filter((id) => rowFor(id) && rowFor(id).scheduled);
  const undated = ids.filter((id) => !rowFor(id) || !rowFor(id).scheduled);
  dated.sort((a, b) => rowFor(a).start_tick - rowFor(b).start_tick);
  return [...dated, ...undated];
}

// -- the editor --------------------------------------------------------------

// plotlineId === null opens an empty draft. `after` is called with
// {saved, deleted, id} so the caller can refresh whatever it is showing.
export async function openPlotlineEditor(book, plotlineId, { after } = {}) {
  const creating = !plotlineId;
  let bookMeta = { title: book, permissions: {} };
  try { bookMeta = await api.getBook(book); } catch (e) { /* fall back to the id */ }

  if (!(bookMeta.permissions || {}).write) {
    toast("You have read access to this book, but not permission to change it.", true);
    return;
  }

  const state = {
    id: plotlineId || "",
    title: "",
    goals: [],
    events: [],
    continuesInto: null,
    rev: null,
    preview: null,      // the last server verdict...
    previewKey: null,   // ...and the candidate it belongs to
    checking: false,
  };
  const rows = new Map(); // event id -> picker row, for scenes not yet previewed
  // Whether the writer has taken the id over from the auto-slug. Lives out here
  // so a re-render does not forget it.
  let idTouched = !creating;
  let focusGoal = false;
  let refocus = null;   // scene id to re-focus after a keyboard move re-renders

  if (!creating) {
    try {
      const pl = await api.getPlotline(book, plotlineId, { expand: true });
      Object.assign(state, {
        title: pl.title || "", goals: pl.goals.slice(), events: pl.events.slice(),
        continuesInto: pl.continues_into, rev: pl.rev, preview: pl,
        previewKey: candidateKey(pl.events, pl.continues_into),
      });
      for (const summary of pl.effective_events) rows.set(summary.id, summaryRow(summary));
    } catch (e) {
      toast(e.isNotFound ? "That plotline does not exist." : "Could not load the plotline.", true);
      return;
    }
  }

  const scope = await loadScope(book);
  const view = el("div", { class: "editor-view" });
  const dialog = modal(
    creating ? "New plotline" : `Edit ${state.title || state.id}`,
    view,
    { wide: true, onClose: () => finish({}) },
  );

  let finished = false;
  function finish(outcome) {
    if (finished) return;
    finished = true;
    dialog.close();
    if (after) after(outcome);
  }

  // -- preview ---------------------------------------------------------------

  let previewTimer = null;
  let previewSeq = 0;

  function candidateKey(events, continuesInto) {
    return JSON.stringify([events, continuesInto || null]);
  }

  function inSync() {
    return state.previewKey === candidateKey(state.events, state.continuesInto);
  }

  async function runPreview() {
    if (!state.events.length) { state.preview = null; state.previewKey = null; return; }
    const mine = ++previewSeq;
    const key = candidateKey(state.events, state.continuesInto);
    state.checking = true;
    try {
      const preview = await api.previewPlotline(book, {
        id: state.id || undefined,
        title: state.title || null,
        events: state.events,
        goals: state.goals,
        continues_into: state.continuesInto,
      });
      if (mine !== previewSeq) return; // a later edit already asked
      state.preview = preview;
      state.previewKey = key;
      for (const summary of preview.effective_events) rows.set(summary.id, summaryRow(summary));
    } catch (e) {
      if (mine !== previewSeq) return;
      state.preview = null;
      state.previewKey = null;
      toast(e.message || "Could not check this ordering.", true);
    } finally {
      if (mine === previewSeq) { state.checking = false; render(); }
    }
  }

  function changed() {
    clearTimeout(previewTimer);
    // Say "checking" from the moment of the change, not when the request
    // finally leaves — otherwise the marks look stale but confident.
    state.checking = state.events.length > 0;
    previewTimer = setTimeout(runPreview, PREVIEW_DEBOUNCE_MS);
    render();
  }

  // -- scene list ------------------------------------------------------------

  // What to draw for each position: the server's verdict when it is current,
  // otherwise the bare scenes we know about, marked as being re-checked.
  function displayRows() {
    if (state.preview && inSync()) {
      return state.preview.effective_events.map(summaryRow);
    }
    // Everything in state.events is this thread's own by definition, whatever a
    // previous preview called it.
    return state.events.map((id) => ({
      ...(rows.get(id) || { id, title: id, when: "…" }), owned: true, findings: [],
    }));
  }

  function removeAt(index) {
    state.events = state.events.filter((_, i) => i !== index);
    changed();
  }

  function moveTo(from, to) {
    if (from === to || to < 0 || to >= state.events.length) return;
    state.events = move(state.events, from, to);
    changed();
  }

  function addScene(row, at = state.events.length) {
    rows.set(row.id, { ...row, owned: true, findings: [] });
    const next = state.events.slice();
    next.splice(at, 0, row.id);
    state.events = next;
    changed();
  }

  // -- rendering -------------------------------------------------------------

  function render() {
    clear(view);
    view.appendChild(detailsFields());
    if (state.preview && inSync()) {
      const banner = problemBanner(state.preview.effective_events, state.preview.status, { onJump: jumpTo });
      if (banner) view.appendChild(banner);
      // A looping continuation would be refused outright on save, so it has to
      // be visible before the writer presses the button.
      const notes = verdictNotes(state.preview.status, state.preview.effective_events);
      if (notes) view.appendChild(notes);
    }
    view.appendChild(sceneSection());
    view.appendChild(actions());
    if (focusGoal) {
      focusGoal = false;
      const input = view.querySelector(".goal-editor input");
      if (input) input.focus();
    }
    if (refocus) {
      const row = view.querySelector(`.scene-row[data-event="${CSS.escape(refocus)}"]`);
      refocus = null;
      if (row) row.focus();
    }
  }

  function detailsFields() {
    const name = el("input", { type: "text", value: state.title, placeholder: state.id || "The Knight's Road" });
    name.addEventListener("input", () => {
      state.title = name.value;
      if (creating && !idTouched) { idBox.value = slugId(name.value); state.id = idBox.value; }
    });

    const idBox = el("input", { type: "text", value: state.id, placeholder: "knights-road", disabled: creating ? null : "" });
    idBox.addEventListener("input", () => { idTouched = true; state.id = idBox.value.trim(); });

    return el("div", { class: "editor-fields" }, [
      labelled("Name", name),
      labelled("Id", idBox, creating
        ? "Used in links and in the API. Derived from the name until you change it."
        : "A plotline's id is permanent."),
      labelled("Goals", goalEditor(), "What this thread is trying to achieve. At least one is required."),
      labelled("Continues into", continuationField(), "Carry on into another thread instead of repeating its scenes."),
    ]);
  }

  function goalEditor() {
    const chips = el("div", { class: "chip-row goal-chips" }, state.goals.map((goal, i) =>
      el("span", { class: "chip goal removable" }, [
        el("span", { text: goal }),
        el("button", { class: "ref-remove", type: "button", text: "✕", title: "Remove goal",
          onclick: () => { state.goals.splice(i, 1); render(); } }),
      ])));
    const input = el("input", { type: "text", placeholder: "Add a goal and press Enter" });
    const commit = (keepFocus) => {
      const goal = input.value.trim();
      if (!goal) return;
      state.goals.push(goal);
      focusGoal = keepFocus; // keep typing: goals usually come in twos and threes
      render();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      commit(true);
    });
    // Take a half-typed goal rather than losing it when the writer clicks away.
    input.addEventListener("blur", () => commit(false));
    return el("div", { class: "goal-editor" }, [chips, input]);
  }

  function continuationField() {
    const current = state.continuesInto;
    const label = current
      ? el("span", { class: "chip", text: current })
      : el("span", { class: "muted", text: "Ends on its own." });
    return el("div", { class: "inline-controls" }, [
      label,
      el("button", { class: "btn secondary sm", type: "button", text: current ? "Change" : "Choose", onclick: chooseContinuation }),
      current ? el("button", { class: "btn secondary sm", type: "button", text: "Clear",
        onclick: () => { state.continuesInto = null; changed(); } }) : null,
    ]);
  }

  function chooseContinuation() {
    const picker = suggestBox({
      placeholder: "Search plotlines…",
      search: (q) => api.listPlotlines(book, { filter: q, perPage: 20 })
        .then((r) => r.plotlines.filter((p) => p.id !== state.id)),
      renderItem: (p) => [
        el("span", { class: "suggest-title", text: p.name }),
        el("span", { class: "suggest-sub muted", text: p.id }),
      ],
      empty: "No other plotline matches.",
      onPick: (p) => { state.continuesInto = p.id; dialog.close(); changed(); },
    });
    const dialog = modal("Continue into which thread?", picker.el);
  }

  function sceneSection() {
    const list = el("div", { class: "editor-scenes" });
    const display = displayRows();
    if (!display.length) {
      list.appendChild(el("p", { class: "empty", text: "No scenes yet — add the first one to begin." }));
    }
    let ownIndex = 0;
    for (const row of display) {
      const index = row.owned ? ownIndex++ : null;
      list.appendChild(sceneRow(row, index));
    }
    return el("div", { class: "editor-section" }, [
      el("div", { class: "section-head" }, [
        el("h2", { class: "section-title", text: "Scenes" }),
        el("span", { class: "muted section-hint",
          text: state.checking ? "checking…" : "drag to reorder, or focus a scene and press ↑ / ↓" }),
      ]),
      list,
      el("div", { class: "editor-scene-actions" }, [
        el("button", { class: "btn secondary sm", type: "button", text: "+ Add scene", onclick: openScenePicker }),
        state.events.length > 1 ? el("button", {
          class: "btn secondary sm", type: "button", text: "Sort by time",
          title: "Put the dated scenes in chronological order",
          onclick: () => { state.events = byTime(state.events, (id) => rows.get(id)); changed(); },
        }) : null,
      ]),
    ]);
  }

  function sceneRow(row, index) {
    const owned = row.owned;
    const node = el("div", {
      class: `scene-row${owned ? "" : " inherited"}${markerClass(row)}`,
      dataset: { event: row.id },
    }, [
      el("div", { class: "scene-handle", title: owned ? "Drag to reorder" : "Inherited — edit it on the thread it belongs to",
        text: owned ? "⠿" : "🔒" }),
      el("div", { class: "scene-main" }, [
        el("div", { class: "scene-head" }, [
          el("span", { class: "scene-when", text: row.when }),
          el("span", { class: "scene-title", text: row.title }),
          owned ? null : el("span", { class: "badge inherited-badge", text: `from ${state.continuesInto}` }),
        ]),
        findingList(book, row, { onJump: jumpTo }),
      ]),
      owned ? el("div", { class: "scene-tools" }, [
        toolButton("↑", "Move up", () => moveTo(index, index - 1), index === 0),
        toolButton("↓", "Move down", () => moveTo(index, index + 1), index === state.events.length - 1),
        toolButton("✎", "Edit this scene", () => editScene(row.id)),
        toolButton("✕", "Remove from this plotline", () => removeAt(index)),
      ]) : null,
    ]);
    if (owned) {
      dragify(node, index, moveTo);
      // The whole row is a reorder control, not just its buttons: focus it and
      // the arrow keys move it, which is faster than the buttons and the only
      // way to reorder without a mouse.
      node.tabIndex = 0;
      node.addEventListener("keydown", (e) => rowKey(e, index));
    }
    return node;
  }

  // Arrow keys move the focused scene and keep focus on it, so a run of presses
  // walks it up the list. Delete removes it. Ignored when the key came from a
  // button inside the row -- those have their own meaning.
  function rowKey(event, index) {
    if (event.target !== event.currentTarget) return;
    const moves = { ArrowUp: index - 1, ArrowDown: index + 1 };
    if (event.key in moves) {
      event.preventDefault();
      const to = moves[event.key];
      if (to < 0 || to >= state.events.length) return;
      refocus = state.events[index];
      moveTo(index, to);
    } else if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      removeAt(index);
    }
  }

  function jumpTo(eventId) {
    const target = view.querySelector(`[data-event="${CSS.escape(eventId)}"]`);
    if (!target) {
      toast("That scene is on another thread.");
      return;
    }
    target.scrollIntoView({ block: "center", behavior: "smooth" });
    target.classList.add("flash");
    setTimeout(() => target.classList.remove("flash"), 1200);
  }

  // -- scene picker / scene form ---------------------------------------------

  function openScenePicker() {
    const body = el("div", { class: "picker-tabs" });
    const dialog = modal("Add a scene", body);
    const chosen = new Set(state.events);

    const existing = suggestBox({
      placeholder: "Search this book's scenes…",
      search: (q) => api.listEvents(book, { filter: q, perPage: 20 }).then((r) => r.events),
      renderItem: (e) => [
        el("span", { class: "suggest-title", text: e.title }),
        el("span", { class: "suggest-sub muted", text: `${e.when} · ${e.location}` }),
        chosen.has(e.id) ? el("span", { class: "chip", text: "already here" }) : null,
      ],
      empty: "No scene matches — write a new one.",
      onPick: (row) => { dialog.close(); addScene(row); },
    });

    const tabs = el("div", { class: "tabs" });
    const panel = el("div", { class: "tab-panel" }, existing.el);
    const select = (which) => {
      clear(panel);
      for (const b of tabs.children) b.classList.toggle("active", b.dataset.tab === which);
      panel.appendChild(which === "existing" ? existing.el : sceneForm(book, {
        scope, calendar: bookMeta.calendar,
        onCancel: dialog.close,
        onSaved: (row) => { dialog.close(); addScene(row); toast(`Added “${row.title}”.`); },
      }));
    };
    for (const [key, label] of [["existing", "An existing scene"], ["new", "Write a new scene"]]) {
      tabs.appendChild(el("button", {
        class: "tab", type: "button", text: label, dataset: { tab: key },
        onclick: () => select(key),
      }));
    }
    body.appendChild(tabs);
    body.appendChild(panel);
    select("existing");
  }

  async function editScene(eventId) {
    let event;
    try {
      event = await api.getEvent(book, eventId);
    } catch (e) {
      toast("Could not open that scene.", true);
      return;
    }
    const holder = el("div");
    const dialog = modal(`Edit “${event.title || event.id}”`, holder);
    holder.appendChild(sceneForm(book, {
      scope, calendar: bookMeta.calendar, event,
      onCancel: dialog.close,
      onSaved: (row) => {
        rows.set(row.id, { ...rows.get(row.id), ...row });
        dialog.close();
        toast(`Saved “${row.title}”.`);
        changed(); // its timing may have fixed (or caused) a conflict
      },
    }));
  }

  // -- save / cancel / delete -------------------------------------------------

  function actions() {
    const problems = [];
    if (!state.id) problems.push("Give the plotline an id.");
    if (!state.events.length) problems.push("A plotline needs at least one of its own scenes.");
    if (!state.goals.length) problems.push("Name at least one goal.");

    return el("div", { class: "editor-actions" }, [
      problems.length ? el("ul", { class: "form-error list" }, problems.map((p) => el("li", { text: p }))) : null,
      el("div", { class: "form-actions" }, [
        el("button", { class: "btn", type: "button", text: creating ? "Create plotline" : "Save changes",
          disabled: problems.length ? "" : null, onclick: save }),
        el("button", { class: "btn secondary", type: "button", text: "Cancel", onclick: () => finish({}) }),
        creating || !(bookMeta.permissions || {}).delete ? null : el("button", {
          class: "btn danger ghost", type: "button", text: "Delete plotline", onclick: confirmDelete,
        }),
      ]),
      el("p", { class: "muted save-note", text: creating
        ? "Nothing is written until you create it."
        : "Findings never block a save — Chronos records what you tell it and reports what does not add up." }),
    ]);
  }

  function body() {
    return {
      title: state.title || null,
      events: state.events,
      goals: state.goals,
      continues_into: state.continuesInto,
    };
  }

  async function save() {
    try {
      const saved = creating
        ? await api.createPlotline(book, state.id, body())
        : await api.updatePlotline(book, state.id, body(), state.rev);
      toast(creating ? "Plotline created." : "Changes saved.");
      finish({ saved: true, id: saved.id });
    } catch (e) {
      if (e.isConflict && e.code === "REVISION_CONFLICT") {
        toast("Someone else changed this plotline — reload before saving.", true);
        return;
      }
      toast(e.message || "Could not save the plotline.", true);
    }
  }

  function confirmDelete() {
    confirmModal(
      `Delete “${state.title || state.id}”?`,
      "The scenes themselves stay in the book; only this thread through them goes away.",
      { yes: "Delete", danger: true, onYes: () => doDelete(false) },
    );
  }

  async function doDelete(inline) {
    try {
      await api.deletePlotline(book, state.id, state.rev, { inline });
      toast("Plotline deleted.");
      finish({ deleted: true, id: state.id });
    } catch (e) {
      if (e.code === "PLOTLINE_IN_USE") return offerInline(e.evidence.plotlines || []);
      toast(e.message || "Could not delete the plotline.", true);
    }
  }

  // Deleting a thread others continue into would orphan them, so the API refuses
  // — unless we first absorb this thread's scenes into each of them, which keeps
  // their stories exactly as they are.
  function offerInline(dependents) {
    confirmModal(
      "Other threads continue into this one",
      el("div", {}, [
        el("p", { text: "These plotlines would lose the rest of their story:" }),
        el("div", { class: "chip-row" }, dependents.map((p) => el("span", { class: "chip", text: p }))),
        el("p", { text: "Copy this thread's scenes into each of them first, so they keep the story they have?" }),
      ]),
      { yes: "Copy in and delete", danger: true, onYes: () => doDelete(true) },
    );
  }

  render();
  if (creating) runPreview();
}

// -- small pieces ------------------------------------------------------------

function summaryRow(summary) {
  return {
    id: summary.id,
    title: summary.title,
    when: eventTimeframe(summary),
    scheduled: summary.scheduled,
    start_tick: summary.start_tick,
    owned: summary.owned !== false,
    findings: summary.findings || [],
  };
}

function slugId(text) {
  return String(text || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function labelled(label, control, hint) {
  return el("div", { class: "field" }, [
    el("label", { class: "field-label", text: label }),
    control,
    hint ? el("p", { class: "field-hint muted", text: hint }) : null,
  ]);
}

function toolButton(glyph, title, onclick, disabled = false) {
  return el("button", {
    class: "icon-btn sm", type: "button", text: glyph, title,
    disabled: disabled ? "" : null, onclick,
  });
}

// -- drag and drop -----------------------------------------------------------

let dragFrom = null;

function dragify(node, index, onMove) {
  node.draggable = true;
  node.addEventListener("dragstart", (e) => {
    dragFrom = index;
    node.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    // Firefox will not start a drag without data on the transfer.
    e.dataTransfer.setData("text/plain", String(index));
  });
  node.addEventListener("dragend", () => {
    dragFrom = null;
    node.classList.remove("dragging");
    node.classList.remove("drop-before", "drop-after");
  });
  node.addEventListener("dragover", (e) => {
    if (dragFrom === null || dragFrom === index) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const after = isBelowMidpoint(e, node);
    node.classList.toggle("drop-before", !after);
    node.classList.toggle("drop-after", after);
  });
  node.addEventListener("dragleave", () => node.classList.remove("drop-before", "drop-after"));
  node.addEventListener("drop", (e) => {
    e.preventDefault();
    node.classList.remove("drop-before", "drop-after");
    if (dragFrom === null || dragFrom === index) return;
    // Dropping below the midpoint means "after this row"; removing the dragged
    // row first shifts later targets down by one.
    let to = isBelowMidpoint(e, node) ? index + 1 : index;
    if (dragFrom < to) to -= 1;
    onMove(dragFrom, to);
  });
}

function isBelowMidpoint(event, node) {
  const box = node.getBoundingClientRect();
  return event.clientY > box.top + box.height / 2;
}
