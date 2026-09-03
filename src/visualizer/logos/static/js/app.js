// The reader, wired up.
//
// Two pages, both real URLs: the shelf at `/`, and one volume at
// `/?book=…&volume=…`. Navigation between them is plain links and full loads
// rather than a client-side router, so the back button, bookmarks and
// "open in new tab" all work without this file owning any history state. The
// one exception is moving between sections of the volume you already have,
// which only rewrites the address bar.
//
// Everything that turns manuscript data into elements lives in `prose.js`
// (rich text) or below (chrome), and both go through the node factory. No
// string of markup is built anywhere in this reader.

import { ApiError, BASE, api } from "./api.js";
import { el, fill, nodeFactory } from "./dom.js";
import { neighbours, sectionLabel, sectionName } from "./navigation.js";
import { RenderError, renderDocument } from "./prose.js";
import {
  DISPLAY_FIELDS,
  FULL,
  otherMode,
  readPreferences,
  resetDisplay,
  showsChronos,
  writePreferences,
} from "./preferences.js";

const root = document.documentElement;
const content = document.getElementById("content");
const toolbar = document.getElementById("reader-toolbar");
const modeButton = document.getElementById("mode-toggle");
const settings = document.getElementById("reading-settings");
const nodes = nodeFactory();
const scenePanels = new Map();
const sectionNodes = new Map();
const contentsLinks = new Map();

let preferences = readPreferences(window.localStorage);
let open = null;
let pager = null;

const MODE_TEXT = {
  focused: ["Focused", "Prose alone — nothing from any other service. Switch to Full view."],
  full: ["Full view", "With the Chronos scenes each section was written from. Switch to Focused."],
};

// The one width where the contents can be a column of its own. Below it the
// panel is a disclosure the reader opens when they want it.
const ROOMY = window.matchMedia("(min-width: 1101px)");

// -- addresses ----------------------------------------------------------------

const home = () => `${BASE}/`;

function readerUrl(book, volume, section) {
  const query = new URLSearchParams({ book });
  if (volume) query.set("volume", volume);
  if (section) query.set("section", section);
  return `${home()}?${query}`;
}

// -- shelf --------------------------------------------------------------------

function bookCard(row) {
  const meta = row.has_manuscript
    ? `${row.volume_count} ${row.volume_count === 1 ? "volume" : "volumes"}`
    : "No manuscript yet";
  const heading = el("h2", { text: row.title || row.book });
  return el("article", { class: `card${row.has_manuscript ? "" : " inert"}` }, [
    row.has_manuscript
      ? el("a", { class: "card-link", href: readerUrl(row.book) }, [heading])
      : heading,
    el("p", { class: "card-sub", text: row.book }),
    el("p", { class: "card-meta", text: meta }),
  ]);
}

function renderShelf(books) {
  document.title = "Logos — manuscripts";
  fill(content, [
    el("div", { class: "page-heading" }, [
      el("p", { class: "eyebrow", text: "Read-only library" }),
      el("h1", { text: "Manuscripts" }),
      el("p", { class: "lead", text: "Choose a manuscript and read it one volume at a time." }),
    ]),
    books.length
      ? el("div", { class: "card-grid" }, books.map(bookCard))
      : el("p", { class: "empty", text: "No readable Chronos books are available." }),
  ]);
}

// -- one volume ---------------------------------------------------------------

function prose(section) {
  try {
    return el("div", { class: "prose" }, [renderDocument(section.document, nodes)]);
  } catch (error) {
    if (!(error instanceof RenderError)) throw error;
    return el("div", { class: "prose" }, [
      el("p", {
        class: "prose-error",
        text: "This section is written with features this reader does not know yet."
          + " Read it through the API until Logos is updated.",
      }),
    ]);
  }
}

function scenePanel(section) {
  if (!(section.event_ids || []).length) return null;
  const panel = el("aside", {
    class: "scenes",
    "aria-label": `Chronos scenes behind ${sectionName(section)}`,
  }, [el("p", { class: "scenes-status", text: "Loading linked scenes…" })]);
  scenePanels.set(section.id, panel);
  return panel;
}

function sectionArticle(section) {
  const article = el("article", { class: "section", id: `section-${section.id}` }, [
    el("header", { class: "section-head" }, [
      section.title ? el("p", { class: "eyebrow", text: sectionLabel(section) }) : null,
      el("h2", { text: sectionName(section) }),
    ]),
    el("div", { class: "section-body" }, [prose(section), scenePanel(section)]),
  ]);
  sectionNodes.set(section.id, article);
  return article;
}

// -- contents -----------------------------------------------------------------

let contents = null;

function contentsLink(section) {
  const link = el("a", {
    href: `#section-${section.id}`,
    text: sectionName(section),
    onclick: (event) => {
      // Continuous reading wants the anchor jump the browser already does.
      // One-section reading has nowhere to jump to, so this *is* the move.
      if (preferences.flow !== "section") return;
      event.preventDefault();
      selectSection(section.id);
      if (!ROOMY.matches) contents.open = false;
    },
  });
  contentsLinks.set(section.id, link);
  return el("li", {}, [link]);
}

function contentsPanel(volume) {
  contents = el("details", {
    class: "contents",
    open: ROOMY.matches,
    "aria-label": "Contents",
  }, [
    el("summary", { class: "contents-summary", text: "Contents" }),
    el("nav", { class: "contents-body", "aria-label": "Sections in this volume" }, [
      el("ol", {}, volume.sections.map(contentsLink)),
    ]),
  ]);
  return contents;
}

/** Wide enough for a column: open it. Narrow: let the reader decide. */
function followWidth(event) {
  if (contents && event.matches) contents.open = true;
}

// -- moving through the volume ------------------------------------------------

function sectionPager() {
  pager = el("nav", { class: "section-pager", "aria-label": "Adjacent sections" });
  return pager;
}

function pagerLink(section, arrow) {
  if (!section) return el("span");
  return el("a", {
    href: readerUrl(open.book, open.volume, section.id),
    text: arrow === "back" ? `← ${sectionName(section)}` : `${sectionName(section)} →`,
    onclick: (event) => {
      event.preventDefault();
      selectSection(section.id);
    },
  });
}

function paintPager() {
  if (!pager || !open) return;
  const { previous, next } = neighbours(open.sections, open.section);
  fill(pager, [pagerLink(previous, "back"), pagerLink(next, "on")]);
}

function selectSection(id) {
  if (!open || !sectionNodes.has(id)) return;
  open.section = id;
  for (const [key, node] of sectionNodes) node.classList.toggle("current", key === id);
  for (const [key, link] of contentsLinks) {
    // Only in one-section reading is there a section you are *on*. Scrolling
    // past a heading is not the same claim, and this reader does not make it.
    const here = key === id && preferences.flow === "section";
    link.classList.toggle("current", here);
    if (here) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");
  }
  paintPager();
  if (preferences.flow === "section") {
    window.history.replaceState(null, "", readerUrl(open.book, open.volume, id));
    window.scrollTo({ top: 0 });
  }
}

function volumeStrip(manuscript, current) {
  if (manuscript.volumes.length < 2) return null;
  return el("nav", { class: "volume-strip", "aria-label": "Volumes" },
    manuscript.volumes.map((row) => el("a", {
      class: `volume-chip${row.id === current ? " current" : ""}`,
      href: readerUrl(manuscript.book, row.id),
      text: row.title,
      ...(row.id === current ? { "aria-current": "page" } : {}),
    })),
  );
}

function volumePager(manuscript, volume) {
  const { previous, next } = neighbours(manuscript.volumes, volume.id);
  const link = (row, text) =>
    row ? el("a", { href: readerUrl(manuscript.book, row.id), text }) : el("span");
  return el("nav", { class: "volume-pager", "aria-label": "Adjacent volumes" }, [
    link(previous, previous ? `← ${previous.title}` : ""),
    link(next, next ? `${next.title} →` : ""),
  ]);
}

function renderReader(manuscript, volume) {
  document.title = `${volume.title} — Logos`;
  scenePanels.clear();
  sectionNodes.clear();
  contentsLinks.clear();
  toolbar.hidden = false;
  fill(content, [
    el("div", { class: "reader-heading" }, [
      el("a", { class: "back-link", href: home(), text: "← Manuscripts" }),
      el("p", { class: "eyebrow", text: manuscript.title || manuscript.book }),
      el("h1", { text: volume.title }),
      el("p", {
        class: "volume-meta",
        text: `Volume ${volume.number} · ${volume.section_count} sections`
          + ` · ${volume.word_count.toLocaleString()} words`,
      }),
      volumeStrip(manuscript, volume.id),
    ]),
    volume.sections.length
      ? el("div", { class: "reader-layout" }, [
          contentsPanel(volume),
          el("div", { class: "manuscript" }, [
            ...volume.sections.map(sectionArticle),
            sectionPager(),
          ]),
        ])
      : el("p", { class: "empty", text: "This volume has no prose yet." }),
    volumePager(manuscript, volume),
  ]);
}

// -- full view ----------------------------------------------------------------

function sceneCard(scene) {
  if (scene.missing) {
    return el("li", { class: "scene gone" }, [
      el("p", { class: "scene-title", text: scene.id }),
      el("p", { class: "scene-when", text: "This scene has been removed from Chronos." }),
    ]);
  }
  return el("li", { class: "scene" }, [
    el("p", { class: "scene-title", text: scene.title }),
    el("p", { class: "scene-when", text: scene.when }),
  ]);
}

function fillScenes(payload) {
  const bySection = new Map(payload.sections.map((row) => [row.section, row.scenes]));
  for (const [section, panel] of scenePanels) {
    fill(panel, [
      el("h3", { text: "Linked scenes" }),
      el("ul", { class: "scene-list" }, (bySection.get(section) || []).map(sceneCard)),
    ]);
  }
}

function sceneLoadFailed(error) {
  const detail = error instanceof ApiError && error.status === 403
    ? "You may read this prose but not the timeline behind it."
    : "The linked scenes could not be loaded.";
  for (const panel of scenePanels.values()) {
    fill(panel, [el("p", { class: "scenes-status", text: detail })]);
  }
}

async function loadScenes() {
  if (!open || open.scenesLoaded || !scenePanels.size) return;
  open.scenesLoaded = true;
  try {
    fillScenes(await api.scenes(open.book, open.volume));
  } catch (error) {
    open.scenesLoaded = false;
    sceneLoadFailed(error);
  }
}

// -- preferences --------------------------------------------------------------

function applyPreferences() {
  for (const field of DISPLAY_FIELDS) {
    root.dataset[field] = preferences[field];
    const control = document.getElementById(`display-${field}`);
    if (control) control.value = preferences[field];
  }
  root.dataset.mode = preferences.mode;
  const [label, hint] = MODE_TEXT[preferences.mode];
  modeButton.textContent = label;
  modeButton.title = hint;
  modeButton.setAttribute("aria-pressed", String(preferences.mode === FULL));
}

function update(patch) {
  const wasFlow = preferences.flow;
  preferences = writePreferences(window.localStorage, patch);
  applyPreferences();
  // Leaving one-section reading puts the whole volume back and takes the
  // section out of the address; entering it has to choose one to be on.
  if (preferences.flow !== wasFlow && open) selectSection(open.section);
  if (preferences.flow === "continuous" && open) {
    window.history.replaceState(null, "", readerUrl(open.book, open.volume));
  }
}

function wire() {
  modeButton.addEventListener("click", () => {
    update({ mode: otherMode(preferences.mode) });
    if (showsChronos(preferences)) loadScenes();
  });
  for (const field of DISPLAY_FIELDS) {
    document.getElementById(`display-${field}`)
      .addEventListener("change", (event) => update({ [field]: event.target.value }));
  }
  document.getElementById("display-reset")
    .addEventListener("click", () => update(resetDisplay(preferences)));
  document.getElementById("settings-open")
    .addEventListener("click", () => settings.showModal());
  ROOMY.addEventListener("change", followWidth);
}

// -- entry --------------------------------------------------------------------

function showFailure(error) {
  toolbar.hidden = true;
  fill(content, [
    el("div", { class: "page-heading" }, [
      el("p", { class: "eyebrow", text: "Logos" }),
      el("h1", { text: "This manuscript could not be opened" }),
      el("p", { class: "lead", text: error.message || "Something went wrong." }),
      el("a", { class: "back-link", href: home(), text: "← Manuscripts" }),
    ]),
  ]);
}

async function openVolume(book, requested, section) {
  const manuscript = await api.manuscript(book);
  const chosen = manuscript.volumes.find((row) => row.id === requested)
    || manuscript.volumes[0];
  if (!chosen) {
    showFailure(new Error(`"${manuscript.title || book}" has no volumes yet.`));
    return;
  }
  const volume = await api.volume(book, chosen.id);
  open = {
    book,
    volume: chosen.id,
    sections: volume.sections,
    section: null,
    scenesLoaded: false,
  };
  renderReader(manuscript, volume);
  const first = volume.sections[0] && volume.sections[0].id;
  selectSection(sectionNodes.has(section) ? section : first);
  if (showsChronos(preferences)) await loadScenes();
}

async function start() {
  wire();
  applyPreferences();
  const query = new URLSearchParams(window.location.search);
  const book = query.get("book");
  if (!book) {
    renderShelf((await api.books()).books);
    return;
  }
  await openVolume(book, query.get("volume"), query.get("section"));
}

start().catch(showFailure);
