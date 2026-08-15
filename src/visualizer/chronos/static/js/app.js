// Orchestrator + hash router for the plotline visualiser.
//
//   #/                        -> pick a book
//   #/~calendars              -> the calendar library (not book-scoped)
//   #/<book>                  -> that book's filtered, paginated plotline table
//   #/<book>/~scenes          -> that book's scene library
//   #/<book>/~issues          -> everything wrong across all of its plotlines
//   #/<book>/~map             -> the story map: every thread, woven
//   #/<book>/~map/<a,b,c>     -> the same, narrowed to the threads you ticked
//   #/<book>/<plotline>       -> one plotline, its events as cards (+ time axis)
//   #/<book>/<plotline>/at/<event> -> the same, scrolled to one scene
//
// Segments are ids, so the library-ish views take names no id can collide with:
// `slugify` strips a leading `~`, so nothing derived from a title can ever be
// `~scenes`, `~issues`, `~map` or `~calendars`. The calendar library sits at the
// top level rather than under a book because that is the whole point of it — a
// calendar outlives any one book, and is chosen while a book is being created.
//
// A selection of threads is worth a link, so it rides in the URL as a
// comma-joined list (the empty list means "all of them"). The old
// `#/<book>/<pl>/connected` route still works and still means what it did: it
// lands on the map with that thread and everything it meets already ticked, and
// rewrites itself to the selection it stands for.
//
// The plotline editor is a modal, not a route: editing is a detour from reading,
// and closing it should put you back exactly where you were.
//
// Each route mounts exactly one view into #content, so only a single plotline is
// ever visualised at a time; the breadcrumbs (and the browser Back button)
// return to the table. Entity references open an article "peek" card in #peek.

import { api, ApiError, BASE } from "./api.js";
import { $ } from "./dom.js";
import { clearPeek, showArticle } from "./peek.js";
import { mountBooks } from "./books.js";
import { mountCalendarLibrary } from "./calendarlibrary.js";
import { mountPlotline } from "./plotline.js";
import { mountBookReport } from "./report.js";
import { mountScenes } from "./scenes.js";
import { mountStoryMap } from "./storymap.js";
import { mountPlotlineTable } from "./table.js";
import { applyFocus } from "./focus.js";
import { initFontScale } from "./fontscale.js";
import { initTheme } from "./theme.js";

const content = $("#content");

// -- navigation --------------------------------------------------------------

// The book-scoped library routes. Reserved: see the note at the top.
const SCENES = "~scenes";
const ISSUES = "~issues";
const CALENDARS = "~calendars";
const MAP = "~map";

const enc = encodeURIComponent;
const go = (hash) => { window.location.hash = hash; };
const toBooks = () => go("#/");
const toBook = (book) => go(`#/${enc(book)}`);
const toScenes = (book) => go(`#/${enc(book)}/${SCENES}`);
const toIssues = (book) => go(`#/${enc(book)}/${ISSUES}`);
const toCalendars = () => go(`#/${CALENDARS}`);
const toPlotline = (book, pl) => go(`#/${enc(book)}/${enc(pl)}`);
// One plotline, opened at a particular scene. The report sends a writer from
// "here is what is wrong" to the scene itself, in the thread it is wrong on.
const toPlotlineAt = (book, pl, ev) =>
  go(ev ? `#/${enc(book)}/${enc(pl)}/at/${enc(ev)}` : `#/${enc(book)}/${enc(pl)}`);
const toConnected = (book, pl) => go(`#/${enc(book)}/${enc(pl)}/connected`);
const toConnectedAt = (book, pl, ev) => go(`#/${enc(book)}/${enc(pl)}/connected/${enc(ev)}`);
// The story map, over a chosen set of threads. An empty list is the whole book,
// which keeps the plain `#/<book>/~map` link meaning what it looks like it means.
const mapHash = (book, ids) =>
  `#/${enc(book)}/${MAP}` + (ids && ids.length ? `/${ids.map(enc).join(",")}` : "");
const toMap = (book) => go(mapHash(book, []));

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  return raw.split("/").filter((s) => s.length).map(decodeURIComponent);
}

// -- the peek slot -----------------------------------------------------------
// Owned by peek.js; these just bind it to whichever book is on screen.

const showEntity = (ref) => showArticle(currentBook, ref);

// -- routing -----------------------------------------------------------------

let currentBook = null;
// Who is logged in, learned once at boot. The calendar library needs it: a
// calendar's identity is (owner, id), so the view has to know which rows are
// the writer's own and under whose name a new one is created.
let me = null;

function route() {
  clearPeek();
  const parts = parseHash();
  currentBook = parts[0] === CALENDARS ? null : (parts[0] || null);
  if (parts.length === 0) {
    mountBooks(content, { onOpen: toBook, onCalendars: toCalendars, onReport: toIssues });
  } else if (parts[0] === CALENDARS) {
    mountCalendarLibrary(content, { onBooks: toBooks, me });
  } else if (parts.length === 1) {
    mountPlotlineTable(content, parts[0], {
      onOpen: (pl) => toPlotline(parts[0], pl),
      onBooks: toBooks,
      onScenes: () => toScenes(parts[0]),
      onIssues: () => toIssues(parts[0]),
      onMap: () => toMap(parts[0]),
    });
  } else if (parts[1] === SCENES) {
    mountScenes(content, parts[0], {
      onBooks: toBooks,
      onBook: () => toBook(parts[0]),
    });
  } else if (parts[1] === ISSUES) {
    mountBookReport(content, parts[0], {
      onBooks: toBooks,
      onBook: () => toBook(parts[0]),
      onScene: (pl, ev) => toPlotlineAt(parts[0], pl, ev),
    });
  } else if (parts[1] === MAP) {
    mountStoryMap(content, parts[0], {
      selection: parts[2] ? parts[2].split(",").filter(Boolean) : [],
      connectedFrom: null,
      focusEvent: null,
      hashFor: (ids) => mapHash(parts[0], ids),
      showEntity,
      onBooks: toBooks,
      onBook: () => toBook(parts[0]),
    });
  } else if (parts[2] === "connected") {
    // The old link into "Connected plots". Same screen now, entered on a preset:
    // the map works out which threads meet this one and rewrites the URL to say
    // so, so what you share is the selection and not how you got to it.
    mountStoryMap(content, parts[0], {
      selection: [],
      connectedFrom: parts[1],
      focusEvent: parts[3] || null,
      hashFor: (ids) => mapHash(parts[0], ids),
      showEntity,
      onBooks: toBooks,
      onBook: () => toBook(parts[0]),
    });
  } else {
    mountPlotline(content, parts[0], parts[1], {
      // `#/<book>/<pl>/at/<event>`: the same timeline, arriving at one scene.
      focusEvent: parts[2] === "at" ? parts[3] || null : null,
      showEntity, onBooks: toBooks, onBook: () => toBook(parts[0]),
      onConnected: () => toConnected(parts[0], parts[1]),
      onConnectedAt: (ev) => toConnectedAt(parts[0], parts[1], ev),
      // The editor is a modal; when it saves under a new id or deletes the
      // thread, the router follows it to wherever it now lives.
      onGone: () => toBook(parts[0]),
      onRenamed: (id) => toPlotline(parts[0], id),
      onSaved: () => route(),
    });
  }
}

// -- boot --------------------------------------------------------------------

function initChrome() {
  initTheme($("#theme-toggle"));
  initFontScale($("#font-toggle"));
  applyFocus(); // restore "hide the marks" from last time
}

async function boot() {
  initChrome();
  try {
    me = (await api.me()).username; // confirm the session before rendering
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.isForbidden)) {
      window.location.href = BASE + "/login";
      return;
    }
  }
  window.addEventListener("hashchange", route);
  route();
}

boot();
