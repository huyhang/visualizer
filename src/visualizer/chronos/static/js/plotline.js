// The single-plotline view: every event as a card, stacked top-to-bottom on a
// vertical timeline (a left rail with a node dot and the scene's timeframe per
// event). Only one plotline is ever shown here (the router mounts one at a
// time), and the breadcrumb returns to the book's plotline table.

import { api } from "./api.js";
import { eventCard, eventTimeframe } from "./cards.js";
import { clear, el } from "./dom.js";
import { allScheduled } from "./timeaxis.js";

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
function timelineRow(book, ev, deps) {
  return el("div", { class: "tl-row" }, [
    el("div", { class: "tl-time", text: eventTimeframe(ev) }),
    el("div", { class: "tl-rail" }, el("span", { class: "tl-dot" })),
    el("div", { class: "tl-card" }, eventCard(book, ev, { ...deps, showTime: false })),
  ]);
}

function verticalTimeline(book, events, deps) {
  return el("div", { class: "timeline-v" }, events.map((ev) => timelineRow(book, ev, deps)));
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
