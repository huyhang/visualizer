// The single-plotline view: every event as a card, stacked top-to-bottom on a
// vertical timeline (a left rail with a node dot and the scene's timeframe per
// event). Only one plotline is ever shown here (the router mounts one at a
// time), and the breadcrumb returns to the book's plotline table.

import { api } from "./api.js";
import { calendarSwitcher, currentFor } from "./calendarview.js";
import { eventCard } from "./cards.js";
import { clear, el } from "./dom.js";
import { findingList, markerClass, problemBanner, verdictNotes } from "./findings.js";
import { focusToggle } from "./focus.js";
import { openPlotlineEditor } from "./plotedit.js";
import { showScene } from "./peek.js";
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

// The rail dot carries both what this scene *is* in the weave and whether it has
// a problem. The marker wins while it is showing -- a contradiction outranks a
// junction for the reader's attention -- and in focus mode the CSS drops the
// marker so the role underneath shows through instead of the dot going blank.
function dotClass(ev) {
  const role = ev.is_terminus ? " is-terminus"
    : ev.is_convergence ? " is-merge"
      : ev.is_divergence ? " is-split" : "";
  return role + markerClass(ev);
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
  return el("div", { class: "tl-row", dataset: { event: ev.id } }, [
    el("div", { class: "tl-time", text: timeLabel }),
    el("div", { class: "tl-rail" }, el("span", { class: "tl-dot" + dotClass(ev) })),
    el("div", { class: "tl-card" }, [
      marks,
      // What is wrong with this scene, above the card so it is read first.
      findingList(book, ev, { onJump: deps.onJump }),
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

// Show a scene a finding names. If it is on this page, scroll to it and flash
// it; if it is not, it belongs to another thread -- open it in the peek panel
// rather than refusing. The cross-thread case is the one worth reaching: a
// conflict with a thread you were not looking at is the thing you could not
// have found any other way.
function jumpTo(container, book, eventId) {
  const target = container.querySelector(`[data-event="${CSS.escape(eventId)}"]`);
  if (!target) {
    showScene(book, { id: eventId });
    return;
  }
  target.scrollIntoView({ block: "center", behavior: "smooth" });
  target.classList.add("flash");
  setTimeout(() => target.classList.remove("flash"), 1200);
}

export async function mountPlotline(container, book, plotlineId,
  { showEntity, onBooks, onBook, onGoal, onConnected, onConnectedAt, onGone, onRenamed, onSaved,
    focusEvent = null }) {
  clear(container);
  const loading = el("div", { class: "view" }, el("p", { class: "muted", text: "Loading plotline…" }));
  container.appendChild(loading);

  // The book comes first now: which calendar the timeline is written in is a
  // property of the book, and the plotline has to be read *through* it.
  let bookMeta = { title: book };
  try { bookMeta = await api.getBook(book); } catch (e) { /* fall back to id */ }
  const calendar = currentFor(book, bookMeta.calendars);

  let pl;
  try {
    pl = await api.getPlotline(book, plotlineId, { expand: true, calendar });
  } catch (e) {
    clear(container);
    container.appendChild(el("div", { class: "view" }, [
      el("p", { class: "empty", text: e.isNotFound ? "That plotline does not exist." : "Could not load the plotline." }),
    ]));
    return;
  }

  const events = pl.effective_events || [];
  const deps = {
    getFullEvent: eventFetcher(book), showEntity, onConnectedAt,
    onJump: (id) => jumpTo(container, book, id),
  };

  // Where to land when the editor closes: the thread is gone, it moved, or it
  // is still here and just needs redrawing.
  const editorClosed = ({ saved, deleted, id }) => {
    if (deleted) return onGone && onGone();
    if (!saved) return;
    if (id && id !== plotlineId) return onRenamed && onRenamed(id);
    if (onSaved) onSaved();
  };

  const goalChip = (ref) => (onGoal && !ref.missing
    ? el("button", { class: "chip goal link", type: "button", text: ref.title,
        title: "Open this goal", onclick: () => onGoal(ref.id) })
    : el("span", { class: "chip goal" + (ref.missing ? " missing" : ""), text: ref.title }));

  const meets = meetCount(events);
  const canEdit = (bookMeta.permissions || {}).write;
  const header = el("div", { class: "pl-header" }, [
    el("h1", { class: "view-title", text: pl.title || pl.id }),
    // The writer's own summary of the thread, above the goals: it says what this
    // is, where the goals say what it is for.
    pl.overview ? el("p", { class: "overview", text: pl.overview }) : null,
    // Goals are records now, so each chip is a link to the goal itself -- where
    // what it rests on, and whether the book delivers it, are answered.
    el("div", { class: "chip-row goals" }, (pl.goal_refs || []).map(goalChip)),
    el("div", { class: "pl-actions" }, [
      canEdit ? el("button", {
        class: "btn sm", type: "button", text: "Edit plotline",
        onclick: () => openPlotlineEditor(book, plotlineId, { after: editorClosed }),
      }) : null,
      // Only offer "Connected plots" when this thread actually meets another; a
      // solo thread would just lead to an empty "runs on its own" view.
      meets ? el("button", {
        class: "btn secondary sm", type: "button",
        text: `Connected plots (${meets})`,
        onclick: () => onConnected && onConnected(),
      }) : null,
      meets ? el("span", { class: "muted meet-hint",
        text: `Meets ${meets} other plotline${meets === 1 ? "" : "s"} along the way.` }) : null,
      // Last, and pushed to the right: a mode switch, not one of the actions.
      // Offered only when there is something to hide.
      events.some((e) => (e.findings || []).length)
        ? focusToggle((pl.status || {}).conflicts) : null,
      // Which reckoning the rail is labelled in. Re-mounts rather than
      // re-labels: every date on the page comes from the server's codec.
      calendarSwitcher(book, bookMeta.calendars, () => mountPlotline(
        container, book, plotlineId,
        { showEntity, onBooks, onBook, onGoal, onConnected, onConnectedAt, onGone, onRenamed,
          onSaved, focusEvent },
      )),
    ].filter(Boolean)),
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
    problemBanner(events, pl.status, { onJump: (id) => jumpTo(container, book, id) }),
    verdictNotes(pl.status, events),
    body,
  ]));

  // Arrived from the book report, which names a scene as well as a thread. The
  // same move the findings' own "show" makes — after a frame, so the rows have
  // been laid out and there is something to scroll to.
  if (focusEvent) requestAnimationFrame(() => jumpTo(container, book, focusEvent));
}
