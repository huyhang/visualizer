// The single-plotline view: every event as a card, stacked top-to-bottom on a
// vertical timeline (a left rail with a node dot and the scene's timeframe per
// event). Only one plotline is ever shown here (the router mounts one at a
// time), and the breadcrumb returns to the book's plotline table.

import { api } from "./api.js";
import { eventCard } from "./cards.js";
import { clear, el } from "./dom.js";
import { allScheduled, groupByPeriod } from "./timeaxis.js";

function breadcrumb(bookTitle, book, plName, onBooks, onBook) {
  return el("nav", { class: "crumbs" }, [
    el("a", { href: "#/", text: "Books", onclick: (e) => { e.preventDefault(); onBooks(); } }),
    el("span", { class: "sep", text: "›" }),
    el("a", { href: `#/${book}`, text: bookTitle, onclick: (e) => { e.preventDefault(); onBook(); } }),
    el("span", { class: "sep", text: "›" }),
    el("span", { text: plName }),
  ]);
}

// A cache so enlarging a card (and re-enlarging it) fetches the full event once.
function eventFetcher(book) {
  const cache = new Map();
  return (id) => {
    if (!cache.has(id)) cache.set(id, api.getEvent(book, id));
    return cache.get(id);
  };
}

// The rail dot picks up this event's role, so the plain timeline already signals
// where threads meet without opening the connected view.
function dotClass(ev) {
  if (ev.is_terminus) return " is-terminus";
  if (ev.is_convergence) return " is-merge";
  if (ev.is_divergence) return " is-split";
  return "";
}

// Small, clickable "another thread meets here" hints on an event. Each opens the
// connected-plots view focused on this event. The terminus is skipped -- every
// thread meets there by rule, so it is a badge on the card, not an interaction.
function eventMarks(ev, onConnectedAt) {
  if (!onConnectedAt || ev.is_terminus) return null;
  const shared = (ev.shared_with || []).length;
  const chips = [];
  if (ev.is_convergence) chips.push(markChip("⋔ threads join here", ev.id, onConnectedAt));
  if (ev.is_divergence) chips.push(markChip("⋔ a thread departs here", ev.id, onConnectedAt));
  if (!chips.length && shared) {
    chips.push(markChip(`shared with ${shared} other thread${shared === 1 ? "" : "s"}`, ev.id, onConnectedAt));
  }
  return chips.length ? el("div", { class: "chip-row tl-marks" }, chips) : null;
}

function markChip(text, eventId, onConnectedAt) {
  return el("button", {
    class: "mark-chip", text, title: "See connected plots",
    onclick: () => onConnectedAt(eventId),
  });
}

// A vertical timeline: one row per event, ordered top-to-bottom (story order).
// The left rail carries a node dot and the scene's timeframe; the card sits to
// its right and expands in place on click, pushing later rows down.
function timelineRow(book, ev, timeLabel, deps) {
  const marks = eventMarks(ev, deps.onConnectedAt);
  return el("div", { class: "tl-row" }, [
    el("div", { class: "tl-time", text: timeLabel }),
    el("div", { class: "tl-rail" }, el("span", { class: "tl-dot" + dotClass(ev) })),
    el("div", { class: "tl-card" }, [
      marks,
      eventCard(book, ev, { ...deps, showTime: false }),
    ].filter(Boolean)),
  ]);
}

const INDENT_REM = 1; // left indent per header level (calendar-driven depth)

function headerRow(level, label) {
  // Level 0 is the prominent top band; deeper levels are muted sub-bands, each
  // indented one more step.
  return el("div", {
    class: level === 0 ? "tl-head tl-head-top" : "tl-head tl-head-sub",
    style: `margin-left:${level * INDENT_REM}rem`,
    text: label,
  });
}

function verticalTimeline(book, events, deps) {
  // Promote coarse calendar components to nested rail headers (year, month, ...),
  // with each period's events grouped beneath so their rail connects and
  // separates cleanly from the next. Depth is decided by the calendar.
  const root = el("div", { class: "timeline-v" });
  let bucket = null;
  for (const item of groupByPeriod(events)) {
    if (item.type === "header") {
      root.appendChild(headerRow(item.level, item.label));
      bucket = null; // a new header starts a fresh event group
    } else {
      if (!bucket) {
        bucket = el("div", { class: "tl-events", style: `margin-left:${item.depth * INDENT_REM}rem` });
        root.appendChild(bucket);
      }
      bucket.appendChild(timelineRow(book, item.event, item.label, deps));
    }
  }
  return root;
}

// How many distinct other threads this plotline meets, ignoring the terminus
// (every thread meets there by rule -- counting it would say "meets everything").
function meetCount(events) {
  const others = new Set();
  for (const e of events) {
    if (e.is_terminus) continue;
    for (const id of e.shared_with || []) others.add(id);
  }
  return others.size;
}

export async function mountPlotline(container, book, plotlineId,
  { showEntity, onBooks, onBook, onConnected, onConnectedAt }) {
  clear(container);
  const loading = el("div", { class: "view" }, el("p", { class: "muted", text: "Loading plotline…" }));
  container.appendChild(loading);

  let pl;
  try {
    pl = await api.getPlotline(book, plotlineId, { expand: true });
  } catch (e) {
    clear(container);
    container.appendChild(el("div", { class: "view" }, [
      el("p", { class: "empty", text: e.isNotFound ? "That plotline does not exist." : "Could not load the plotline." }),
    ]));
    return;
  }

  let bookMeta = { title: book };
  try { bookMeta = await api.getBook(book); } catch (e) { /* fall back to id */ }

  const events = pl.effective_events || [];
  const deps = { getFullEvent: eventFetcher(book), showEntity, onConnectedAt };

  const meets = meetCount(events);
  const header = el("div", { class: "pl-header" }, [
    el("h1", { class: "view-title", text: pl.title || pl.id }),
    el("div", { class: "chip-row goals" }, (pl.goals || []).map((g) => el("span", { class: "chip goal", text: g }))),
    // Only offer "Connected plots" when this thread actually meets another; a
    // solo thread would just lead to an empty "runs on its own" view.
    meets ? el("div", { class: "pl-actions" }, [
      el("button", {
        class: "btn secondary sm", type: "button",
        text: `Connected plots (${meets})`,
        onclick: () => onConnected && onConnected(),
      }),
      el("span", { class: "muted meet-hint",
        text: `Meets ${meets} other plotline${meets === 1 ? "" : "s"} along the way.` }),
    ]) : null,
    el("p", { class: "muted axis-note", text: allScheduled(events)
      ? "Scenes top to bottom in story order — all are scheduled."
      : "Scenes top to bottom in story order — some have no timing yet." }),
  ]);

  clear(container);
  const body = events.length
    ? verticalTimeline(book, events, deps)
    : el("p", { class: "empty", text: "This plotline has no events." });
  container.appendChild(el("div", { class: "view plotline-view" }, [
    breadcrumb(bookMeta.title || book, book, pl.title || pl.id, onBooks, onBook),
    header,
    body,
  ]));
}
