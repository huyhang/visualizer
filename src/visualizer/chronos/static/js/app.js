// Orchestrator + hash router for the plotline visualiser.
//
//   #/                        -> pick a book
//   #/<book>                  -> that book's filtered, paginated plotline table
//   #/<book>/~scenes          -> that book's scene library
//   #/<book>/<plotline>       -> one plotline, its events as cards (+ time axis)
//
// The second segment is a plotline id, so the scene library takes a name no id
// can collide with: `slugify` strips the leading `~`, so no id derived from a
// title can ever be `~scenes`.
//
// The plotline editor is a modal, not a route: editing is a detour from reading,
// and closing it should put you back exactly where you were.
//
// Each route mounts exactly one view into #content, so only a single plotline is
// ever visualised at a time; the breadcrumbs (and the browser Back button)
// return to the table. Entity references open an article "peek" card in #peek.

import { api, ApiError, BASE } from "./api.js";
import { $ } from "./dom.js";
import { clearPeek, showArticle, showScene } from "./peek.js";
import { mountBooks } from "./books.js";
import { mountPlotline } from "./plotline.js";
import { mountScenes } from "./scenes.js";
import { mountConnected } from "./storygraph.js";
import { mountPlotlineTable } from "./table.js";
import { applyFocus } from "./focus.js";
import { initFontScale } from "./fontscale.js";
import { initTheme } from "./theme.js";

const content = $("#content");

// -- navigation --------------------------------------------------------------

// The scene library's route segment. Reserved: see the note at the top.
const SCENES = "~scenes";

const enc = encodeURIComponent;
const go = (hash) => { window.location.hash = hash; };
const toBooks = () => go("#/");
const toBook = (book) => go(`#/${enc(book)}`);
const toScenes = (book) => go(`#/${enc(book)}/${SCENES}`);
const toPlotline = (book, pl) => go(`#/${enc(book)}/${enc(pl)}`);
const toConnected = (book, pl) => go(`#/${enc(book)}/${enc(pl)}/connected`);
const toConnectedAt = (book, pl, ev) => go(`#/${enc(book)}/${enc(pl)}/connected/${enc(ev)}`);

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  return raw.split("/").filter((s) => s.length).map(decodeURIComponent);
}

// -- the peek slot -----------------------------------------------------------
// Owned by peek.js; these just bind it to whichever book is on screen.

const showEntity = (ref) => showArticle(currentBook, ref);
const showEventPeek = (node) => showScene(currentBook, node);

// -- routing -----------------------------------------------------------------

let currentBook = null;

function route() {
  clearPeek();
  const parts = parseHash();
  currentBook = parts[0] || null;
  if (parts.length === 0) {
    mountBooks(content, { onOpen: toBook });
  } else if (parts.length === 1) {
    mountPlotlineTable(content, parts[0], {
      onOpen: (pl) => toPlotline(parts[0], pl),
      onBooks: toBooks,
      onScenes: () => toScenes(parts[0]),
    });
  } else if (parts[1] === SCENES) {
    mountScenes(content, parts[0], {
      onBooks: toBooks,
      onBook: () => toBook(parts[0]),
    });
  } else if (parts[2] === "connected") {
    mountConnected(content, parts[0], parts[1], {
      focusEvent: parts[3] || null,
      showEventPeek,
      onBooks: toBooks,
      onBook: () => toBook(parts[0]),
      onTimeline: () => toPlotline(parts[0], parts[1]),
      onPlotline: (pl) => toConnected(parts[0], pl),
    });
  } else {
    mountPlotline(content, parts[0], parts[1], {
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
    await api.me(); // confirm the session before rendering
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
