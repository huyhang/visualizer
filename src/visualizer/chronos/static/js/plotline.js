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

// A vertical timeline: one row per event, ordered top-to-bottom (story order).
// The left rail carries a node dot and the scene's timeframe; the card sits to
// its right and expands in place on click, pushing later rows down.
function timelineRow(book, ev, timeLabel, deps) {
  return el("div", { class: "tl-row" }, [
    el("div", { class: "tl-time", text: timeLabel }),
    el("div", { class: "tl-rail" }, el("span", { class: "tl-dot" })),
    el("div", { class: "tl-card" }, eventCard(book, ev, { ...deps, showTime: false })),
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

export async function mountPlotline(container, book, plotlineId, { showEntity, onBooks, onBook }) {
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
  const deps = { getFullEvent: eventFetcher(book), showEntity };

  const header = el("div", { class: "pl-header" }, [
    el("h1", { class: "view-title", text: pl.title || pl.id }),
    el("div", { class: "chip-row goals" }, (pl.goals || []).map((g) => el("span", { class: "chip goal", text: g }))),
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
