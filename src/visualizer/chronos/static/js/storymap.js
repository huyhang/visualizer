// The story map: pick any number of the book's threads and see how they weave.
//
// This module is the impure shell -- fetch, picker, state, mount -- around four
// pure steps it drives in order:
//
//   subgraph.restrictTo   which threads are in
//   collapse.collapseRuns how dense the result is
//   layout.layoutGraph    where everything goes
//   storygraph.diagram    what it looks like
//
// "Connected plots" is not a separate view any more, just a preset: arriving
// from a plotline preselects that thread and everything it meets, then rewrites
// the URL to the selection it stands for, so the two are the same screen.
//
// State that is worth a link (which threads) lives in the URL. State that is
// worth only the session (which scenes are open, how dense the rows are) lives
// here, and survives a re-slice -- ticking a thread on must not shut the scene
// you were reading.

import { api } from "./api.js";
import { eventPeekCard } from "./cards.js";
import { calendarSwitcher, currentFor } from "./calendarview.js";
import { clear, el } from "./dom.js";
import { collapseRuns } from "./collapse.js";
import { applyPeriodGrouping, geometry, layoutGraph, paletteColor, paletteDash } from "./layout.js";
import { connectedIds, restrictTo } from "./subgraph.js";
import { diagram, swatch } from "./storygraph.js";

// Room under an expanded card before the next row starts.
const CARD_GAP = 14;
// A redraw can change a measured height, which asks for another redraw. Two
// passes settle every real case (measure, then re-measure after the reflow);
// the cap is only there so a pathological layout cannot spin.
const MEASURE_PASSES = 3;

function breadcrumb(bookTitle, { onBooks, onBook }) {
  return el("nav", { class: "crumbs" }, [
    el("a", { href: "#/", text: "Books", onclick: (e) => { e.preventDefault(); onBooks(); } }),
    el("span", { class: "sep", text: "›" }),
    el("a", { href: "#/", text: bookTitle, onclick: (e) => { e.preventDefault(); onBook(); } }),
    el("span", { class: "sep", text: "›" }),
    el("span", { text: "Story Map" }),
  ]);
}

// What a calendar switch has to hand the remount.
//
// Switching calendars rebuilds the whole map, because every label on it changes.
// The `deps` this view was mounted with are frozen at route entry, though, and
// the selection has moved since: ticking a thread writes the new list with
// `replaceState` precisely so the router does *not* remount. So reusing `deps`
// verbatim rebuilds the map from a selection the writer abandoned, silently
// undoing every tick they have made since they arrived.
//
// `connectedFrom` is dropped for the same reason. It is how the view was
// *entered* -- "this thread and everything it meets" -- and re-deriving from it
// would beat the explicit selection that has since replaced it. An empty list
// means "all of them", matching what `hashFor` writes to the URL.
export function remountDeps(deps, bookOrder, selected) {
  const everything = selected.size === bookOrder.length;
  return {
    ...deps,
    selection: everything ? [] : bookOrder.filter((id) => selected.has(id)),
    connectedFrom: null,
  };
}

// A thread's toggle. The swatch is the lane's own colour and stroke, so what you
// click is what you get -- and a thread that is off still shows its mark, which
// is what makes the picker read as a legend too.
function threadChip(lane, on, onToggle) {
  return el("button", {
    class: "sg-pick" + (on ? " is-on" : ""),
    type: "button",
    "aria-pressed": on ? "true" : "false",
    title: on ? `Hide “${lane.title}”` : `Show “${lane.title}”`,
    onclick: () => onToggle(lane.id),
  }, [swatch(lane), el("span", { text: lane.title })]);
}

const words = (q) => q.toLowerCase().split(/\s+/).filter(Boolean);
const matches = (title, terms) => {
  const hay = title.toLowerCase();
  return terms.every((w) => hay.includes(w));
};

export async function mountStoryMap(container, book, deps) {
  const {
    selection, connectedFrom, focusEvent, hashFor,
    showEntity, onBooks, onBook,
  } = deps;

  clear(container);
  container.appendChild(el("div", { class: "view" },
    el("p", { class: "muted", text: "Loading the Story Map…" })));

  // The book first: the graph's node labels are written in one of its calendars,
  // so the choice has to be known before the graph is asked for.
  let bookMeta = { title: book };
  try { bookMeta = await api.getBook(book); } catch (e) { /* fall back to the id */ }

  let graph;
  try {
    graph = await api.getGraph(book, { calendar: currentFor(book, bookMeta.calendars) });
  } catch (e) {
    clear(container);
    container.appendChild(el("div", { class: "view" },
      el("p", { class: "empty", text: "Could not load the story graph." })));
    return;
  }

  const all = graph.plotlines || [];
  const view = el("div", { class: "view map-view" });
  view.appendChild(breadcrumb(bookMeta.title || book, { onBooks, onBook }));

  if (!all.length) {
    view.appendChild(el("h1", { class: "view-title", text: "Story Map" }));
    view.appendChild(el("p", { class: "empty", text:
      "This book has no plotlines yet, so there is nothing to map." }));
    clear(container);
    container.appendChild(view);
    return;
  }

  // -- state -----------------------------------------------------------------

  // Colour is keyed to a thread's place in the whole book (the graph is
  // name-ordered), so it is the same in every view and never shifts when the
  // selection does. Only the *column* adapts -- see layout.orderLanes.
  const bookOrder = all.map((p) => p.id);
  const indexOf = (id) => bookOrder.indexOf(id);
  const colorOf = (id) => paletteColor(indexOf(id));
  const dashOf = (id) => paletteDash(indexOf(id));

  const known = new Set(bookOrder);
  // Arriving from a plotline: that thread plus everything it meets. Otherwise
  // whatever the URL asked for, and failing that the whole book.
  let focusPl = null;
  let selected;
  if (connectedFrom && known.has(connectedFrom)) {
    focusPl = connectedFrom;
    selected = connectedIds(graph, connectedFrom);
  } else if (selection && selection.length) {
    selected = new Set(selection.filter((id) => known.has(id)));
  } else {
    selected = new Set(bookOrder);
  }
  if (!selected.size) selected = new Set(bookOrder);

  const openEvents = new Set();
  const openBands = new Set();
  // Moments whose scenes the writer has hidden. Shown is the default: a scene you
  // cannot read is not much of a map.
  const collapsedMoments = new Set();
  const heights = new Map(); // event id -> measured height of its expanded row
  const cards = new Map();   // event id -> its card, so unfolding twice fetches once
  let compact = false;

  const rowHeight = () => (compact ? geometry.ROW_COMPACT : geometry.ROW_H);
  // A slot's height. Measured once it is on screen (heights, keyed by the same id
  // the row carries); until then an estimate good enough not to jump visibly --
  // a merged group needs a line per scene, an open card rather more.
  const heightOf = (slot) => {
    const measured = heights.get(slot.id);
    if (measured) return measured;
    if (slot.isGroup) {
      return slot.collapsed
        ? rowHeight()
        : rowHeight() + (slot.count - 1) * (rowHeight() * 0.55);
    }
    return openEvents.has(slot.id) ? rowHeight() * 3 : rowHeight();
  };

  // -- chrome ----------------------------------------------------------------

  const title = el("h1", { class: "view-title", text: "Story Map" });
  const note = el("p", { class: "muted axis-note" });
  const picker = el("div", { class: "sg-picker" });
  const canvas = el("div", { class: "sg-canvas" });
  const footnote = el("p", { class: "muted axis-note" });

  const filterBox = el("input", {
    type: "search", class: "filter-box sm", placeholder: "Filter threads…",
    autocomplete: "off",
  });

  const densityBtn = el("button", {
    class: "btn secondary sm", type: "button", text: "Compact",
    title: "Tighter rows — more of the story on one screen",
    onclick: () => {
      compact = !compact;
      densityBtn.textContent = compact ? "Roomy" : "Compact";
      redraw();
    },
  });

  // Every solitary stretch the last draw found, folded or not -- what "Unfold
  // all" works from, and what the footnote counts.
  let lastBands = [];

  const foldBtn = el("button", {
    class: "btn secondary sm", type: "button", text: "Unfold all",
    title: "Show every scene, including the stretches a thread walks alone",
    onclick: () => {
      if (openBands.size) openBands.clear();
      else lastBands.forEach((b) => openBands.add(b.id));
      redraw();
    },
  });

  const selectAll = (on) => {
    selected = new Set(on ? bookOrder : []);
    focusPl = null;
    rebuild();
  };

  // "Everything except these two" is a real way to read a book, and awkward to
  // express by clicking every other chip.
  const invert = () => {
    selected = new Set(bookOrder.filter((id) => !selected.has(id)));
    focusPl = null;
    rebuild();
  };

  const toggleThread = (id) => {
    if (selected.has(id)) selected.delete(id);
    else selected.add(id);
    focusPl = null; // the writer is steering now, not the preset that brought them
    rebuild();
  };

  function paintPicker() {
    clear(picker);
    const terms = words(filterBox.value.trim());
    const shown = all.filter((p) => matches(p.title || p.id, terms));
    if (!shown.length) {
      picker.appendChild(el("span", { class: "muted", text: "No threads match your filter." }));
      return;
    }
    for (const p of shown) {
      picker.appendChild(threadChip(
        { id: p.id, title: p.title || p.id, color: colorOf(p.id), dash: dashOf(p.id) },
        selected.has(p.id), toggleThread,
      ));
    }
  }

  // -- the drawing -----------------------------------------------------------

  function cardFor(node) {
    if (!cards.has(node.id)) {
      const card = eventPeekCard(book, node, {
        showEntity,
        onClose: () => { openEvents.delete(node.id); heights.delete(node.id); redraw(); },
      });
      // The card fills in after its fetch, and taller content has to push the
      // rows below it down -- so the row is re-measured whenever the card
      // changes size, not just when it opens.
      if (typeof ResizeObserver === "function") {
        new ResizeObserver(() => measure()).observe(card);
      }
      cards.set(node.id, card);
    }
    return cards.get(node.id);
  }

  // Every redraw rebuilds the rows, so the element the writer was standing on
  // stops existing -- and an expanded row is redrawn *twice*, once to open it and
  // again once its card has been measured. Focus therefore has to be restored
  // after each pass, not just the first, or Esc has nothing to arrive at. The id
  // is held until the measuring settles, then dropped, so an unrelated redraw
  // (typing in the filter box) never steals the cursor.
  let toggled = null;
  function restoreFocus() {
    if (!toggled) return;
    const head = canvas.querySelector(`[data-event="${CSS.escape(toggled)}"] .sg-row-head`);
    if (head) head.focus();
  }

  const onToggleEvent = (node) => {
    if (openEvents.has(node.id)) { openEvents.delete(node.id); heights.delete(node.id); }
    else openEvents.add(node.id);
    toggled = node.id;
    redraw();
  };

  const onToggleBand = (node) => {
    if (openBands.has(node.id)) openBands.delete(node.id);
    else openBands.add(node.id);
    redraw();
  };

  // Hide a moment's scenes behind their count, or show them again.
  const onToggleGroup = (id) => {
    if (collapsedMoments.has(id)) collapsedMoments.delete(id);
    else collapsedMoments.add(id);
    heights.delete(id); // an open moment's height says nothing about a closed one
    redraw();
  };

  // An expanded row's height is whatever the browser made it, so it can only be
  // known after a paint. Measure, and if anything moved, lay out again with the
  // real numbers.
  let passes = 0;
  let pending = false;
  function measure() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      let changed = false;
      for (const row of canvas.querySelectorAll(".sg-row.expanded, .sg-row.is-group:not(.collapsed)")) {
        const id = row.dataset.event || row.dataset.slot;
        const h = row.offsetHeight + CARD_GAP;
        if (Math.abs((heights.get(id) || 0) - h) > 1) { heights.set(id, h); changed = true; }
      }
      if (changed && passes < MEASURE_PASSES) { passes++; redraw(); }
      else { passes = 0; toggled = null; } // settled: stop chasing the cursor
    });
  }

  function redraw() {
    if (!selected.size) {
      clear(canvas);
      canvas.appendChild(el("p", { class: "empty", text:
        "No threads selected — tick one above to start the map." }));
      lastBands = [];
      foldBtn.hidden = true;
      footnote.textContent = "";
      return;
    }
    const slice = restrictTo(graph, selected, focusPl);
    const dense = collapseRuns(slice, { expanded: openBands });
    lastBands = dense.bands || [];
    const layout = layoutGraph(dense, { colorOf, dashOf, heightOf });
    const model = applyPeriodGrouping(layout, { heightOf, collapsedMoments });

    clear(canvas);
    canvas.appendChild(diagram(model, {
      expanded: openEvents, cardFor, onToggleEvent, onToggleBand, onToggleGroup,
      focusEvent,
    }));

    const folded = lastBands.filter((b) => !openBands.has(b.id));
    const hidden = folded.reduce((n, b) => n + b.events.length, 0);
    foldBtn.hidden = !lastBands.length;
    foldBtn.textContent = openBands.size ? "Fold solo runs" : "Unfold all";
    footnote.textContent = [
      hidden ? `${hidden} scenes are folded into ${folded.length} solitary `
        + `stretch${folded.length === 1 ? "" : "es"} — click one to unfold it.` : "",
      // What the underline means. Said once, under the drawing, rather than
      // carried as a badge on the one row that can least afford the width.
      layout.nodes.some((n) => n.isTerminus)
        ? "The underlined scene is this book's ending — every thread must reach it."
        : "",
      layout.hasUnscheduled
        ? "Some scenes have no timing yet; they sit between the dated scenes "
          + "either side of them." : "",
    ].filter(Boolean).join(" ");

    restoreFocus();
    measure();
  }

  // A change of selection: repaint the picker, redraw, and put the new selection
  // in the URL. `replaceState` rather than a hash assignment, because the router
  // would remount the whole view and take every open scene with it.
  // What the count says has to be actionable, because a selection outlives the
  // book it was made from: the URL carries an explicit list, so a link written
  // before a thread existed quietly leaves it out for good. A bare "6 of 8" is
  // true and useless -- it reads as a fact about the book rather than as
  // something you can undo.
  function paintNote() {
    clear(note);
    if (selected.size === all.length) {
      note.appendChild(el("span", { text: `Every thread in this book — ${all.length}.` }));
      return;
    }
    const hidden = all.length - selected.size;
    note.appendChild(el("span", {
      text: `${selected.size} of ${all.length} threads — ${hidden} not shown`,
    }));
    note.appendChild(el("span", { class: "sep", text: "·" }));
    note.appendChild(el("button", {
      class: "link-btn", type: "button", text: "Show all",
      title: "Add the threads this selection leaves out",
      onclick: () => selectAll(true),
    }));
  }

  function rebuild() {
    paintPicker();
    paintNote();
    redraw();
    if (hashFor) {
      const ids = selected.size === all.length ? [] : bookOrder.filter((id) => selected.has(id));
      window.history.replaceState(null, "", hashFor(ids));
    }
  }

  filterBox.addEventListener("input", paintPicker);

  view.appendChild(el("div", { class: "pl-header" }, [
    title,
    calendarSwitcher(book, bookMeta.calendars,
      () => mountStoryMap(container, book, remountDeps(deps, bookOrder, selected))),
    note,
  ]));
  view.appendChild(el("div", { class: "sg-controls" }, [
    filterBox,
    el("button", { class: "btn secondary sm", type: "button", text: "All",
      title: "Show every thread", onclick: () => selectAll(true) }),
    el("button", { class: "btn secondary sm", type: "button", text: "None",
      title: "Clear the selection", onclick: () => selectAll(false) }),
    el("button", { class: "btn secondary sm", type: "button", text: "Invert",
      title: "Swap which threads are shown for which are not", onclick: invert }),
    densityBtn,
    foldBtn,
  ]));
  view.appendChild(picker);
  view.appendChild(canvas);
  view.appendChild(footnote);

  clear(container);
  container.appendChild(view);
  rebuild();

  // If we arrived at a particular scene, bring it into view.
  if (focusEvent) {
    const row = view.querySelector(".sg-row.focused");
    if (row) row.scrollIntoView({ block: "center" });
  }
}
