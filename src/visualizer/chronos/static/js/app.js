// Orchestrator + hash router for the read-only plotline visualiser.
//
//   #/                     -> pick a book
//   #/<book>               -> that book's filtered, paginated plotline table
//   #/<book>/<plotline>    -> one plotline, its events as cards (+ time axis)
//
// Each route mounts exactly one view into #content, so only a single plotline is
// ever visualised at a time; the breadcrumbs (and the browser Back button)
// return to the table. Entity references open an article "peek" card in #peek.

import { api, ApiError, BASE } from "./api.js";
import { articleCard } from "./cards.js";
import { $, clear } from "./dom.js";
import { mountBooks } from "./books.js";
import { mountPlotline } from "./plotline.js";
import { mountPlotlineTable } from "./table.js";
import { initFontScale } from "./fontscale.js";
import { initTheme } from "./theme.js";

const content = $("#content");
const peek = $("#peek");

// -- navigation --------------------------------------------------------------

const enc = encodeURIComponent;
const go = (hash) => { window.location.hash = hash; };
const toBooks = () => go("#/");
const toBook = (book) => go(`#/${enc(book)}`);
const toPlotline = (book, pl) => go(`#/${enc(book)}/${enc(pl)}`);

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  return raw.split("/").filter((s) => s.length).map(decodeURIComponent);
}

// -- entity peek card --------------------------------------------------------

function clearPeek() { clear(peek); }

function showEntity(ref) {
  clear(peek);
  peek.appendChild(articleCard(currentBook, ref, { onClose: clearPeek }));
}

// -- routing -----------------------------------------------------------------

let currentBook = null;

function route() {
  clearPeek();
  const parts = parseHash();
  currentBook = parts[0] || null;
  if (parts.length === 0) {
    mountBooks(content, { onOpen: toBook });
  } else if (parts.length === 1) {
    mountPlotlineTable(content, parts[0], { onOpen: (pl) => toPlotline(parts[0], pl), onBooks: toBooks });
  } else {
    mountPlotline(content, parts[0], parts[1], {
      showEntity, onBooks: toBooks, onBook: () => toBook(parts[0]),
    });
  }
}

// -- boot --------------------------------------------------------------------

function initChrome() {
  initTheme($("#theme-toggle"));
  initFontScale($("#font-toggle"));
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
