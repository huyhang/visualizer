// Which of a book's calendars the writer is currently reading through.
//
// A book may keep several parallel reckonings — different cultures counting the
// same events, some of which ended when their culture did. They are parallel
// *labellings* of one canonical tick line, never parallel timelines: switching
// changes what the dates say and nothing else. No scene moves, no ordering
// changes, no verdict differs. That is why this is a view preference rather
// than a route: it is closer to the theme toggle than to navigation.
//
// The choice is remembered per book in localStorage, so returning to a book
// lands in the reckoning you left it in. The trade-off is that a link you send
// someone opens in *their* last choice, not yours; if a shareable
// "…#/book?calendar=elvish" is ever wanted, this module is the only thing that
// would have to learn about the hash.
//
// No formatting happens here, or anywhere else in the browser. Labels come from
// the server's codec — the same rule `calendars.js` follows and for the same
// reason: a second mixed-radix implementation is one that can disagree.

import { el } from "./dom.js";

const KEY = "chronos.calendarView";

function stored() {
  try {
    return JSON.parse(window.localStorage.getItem(KEY) || "{}") || {};
  } catch (e) {
    return {}; // unreadable or disabled storage is simply no preference
  }
}

function persist(map) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(map));
  } catch (e) { /* private mode: the choice just does not outlive the page */ }
}

// The remembered choice, *validated against what the book actually has now*.
// A calendar the writer detached since would otherwise 404 every read on the
// page — the server refuses an unattached name rather than falling back, which
// is right for a typo'd URL and wrong for a stale preference. Checking here is
// what tells the two apart.
export function currentFor(book, calendars = []) {
  const chosen = stored()[book];
  if (!chosen) return null;
  return (calendars || []).some((c) => c.id === chosen) ? chosen : null;
}

export function setFor(book, calendarId) {
  const map = stored();
  // The primary needs no entry: storing "the default" would pin a book to
  // whichever calendar happened to be first on the day the writer looked.
  if (calendarId) map[book] = calendarId;
  else delete map[book];
  persist(map);
}

export function labelFor(calendars, calendarId) {
  const found = (calendars || []).find((c) => c.id === calendarId);
  return found ? found.label : null;
}

// The control itself: absent unless there is a genuine choice to make, so a
// book with one calendar (which is most books) gains no chrome at all.
export function calendarSwitcher(book, calendars, onChange) {
  if ((calendars || []).length < 2) return null;
  const current = currentFor(book, calendars) || calendars[0].id;

  const choose = el("select", { class: "calendar-switch", "aria-label": "Read dates in" },
    calendars.map((c) => el("option", {
      value: c.id,
      text: c.label,
      title: eraNote(c) || undefined,
    })));
  choose.value = current;
  choose.addEventListener("change", () => {
    // The primary is stored as "no preference" so it survives a reorder.
    setFor(book, choose.value === calendars[0].id ? null : choose.value);
    onChange(currentFor(book, calendars));
  });

  return el("label", { class: "calendar-switcher" }, [
    el("span", { class: "muted sm", text: "Dates in" }),
    choose,
  ]);
}

// "kept from tick 100 until tick 300" — what makes a reckoning that ended
// legible in the picker, rather than the writer wondering why half their scenes
// read "before Elvish Count".
export function eraNote(calendar) {
  const { from_tick: from, until_tick: until } = calendar || {};
  if (from == null && until == null) return "";
  if (from != null && until != null) return `Kept from tick ${from} until ${until}.`;
  if (from != null) return `Kept from tick ${from} onwards.`;
  return `Kept until tick ${until}.`;
}
