// Logos' three-page reader: manuscript shelf, book contents, and one section.
// Navigation uses ordinary links and full page loads so bookmarks, new tabs,
// and the browser's back button work without a client-side router.

import { ApiError, BASE, api } from "./api.js";
import { boundaryGesture } from "./boundary.js";
import { el, fill, nodeFactory, svgEl } from "./dom.js";
import {
  findSection,
  sectionAhead,
  sectionLabel,
  sectionName,
  sectionNeighbours,
} from "./navigation.js";
import {
  defaultOpenVolume,
  filterOutline,
  pageForSection,
  SECTION_PAGE_SIZE,
  sectionCount,
  sectionPage,
} from "./outline.js";
import {
  blockAnchor,
  forgetPosition,
  prunePositions,
  readPosition,
  scrollForAnchor,
  storePosition,
  writePosition,
} from "./position.js";
import {
  DISPLAY_FIELDS,
  FULL,
  otherMode,
  readPreferences,
  resetDisplay,
  showsChronos,
  writePreferences,
} from "./preferences.js";
import { sectionProgress, scrollForProgress } from "./progress.js";
import { RenderError, renderDocument } from "./prose.js";
import {
  bookmarkAt,
  bookmarks as bookmarkItems,
  dataForSection,
  removeItem,
  replaceItem,
} from "./readerdata.js";

const root = document.documentElement;
const content = document.getElementById("content");
const toolbar = document.getElementById("reader-toolbar");
const modeButton = document.getElementById("mode-toggle");
const settings = document.getElementById("reading-settings");
const progressRegion = document.getElementById("reading-progress");
const progressMeter = document.getElementById("reading-progress-meter");
const progressValue = document.getElementById("reading-progress-value");
const jumpButton = document.getElementById("jump-open");
const jumpDialog = document.getElementById("section-jump");
const jumpSearch = document.getElementById("jump-search");
const jumpStatus = document.getElementById("jump-status");
const jumpResults = document.getElementById("jump-results");
const searchButton = document.getElementById("search-open");
const searchDialog = document.getElementById("manuscript-search");
const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("manuscript-search-input");
const searchStatus = document.getElementById("search-status");
const searchResults = document.getElementById("search-results");
const bookmarksButton = document.getElementById("bookmarks-open");
const bookmarksDialog = document.getElementById("bookmarks-dialog");
const bookmarksStatus = document.getElementById("bookmarks-status");
const bookmarksResults = document.getElementById("bookmarks-results");
const itemEditor = document.getElementById("item-editor");
const itemEditorForm = document.getElementById("item-editor-form");
const itemEditorTitle = document.getElementById("item-editor-title");
const itemEditorText = document.getElementById("item-editor-text");
const itemEditorError = document.getElementById("item-editor-error");
const itemEditorDelete = document.getElementById("item-editor-delete");
const publicationDialog = document.getElementById("publication-dialog");
const publicationForm = document.getElementById("publication-form");
const publicationFields = document.getElementById("publication-fields");
const publicationCover = document.getElementById("publication-cover");
const publicationError = document.getElementById("publication-error");
const coverDelete = document.getElementById("cover-delete");
const exportEpubButton = document.getElementById("export-epub");
const exportPdfButton = document.getElementById("export-pdf");
const syncControl = document.getElementById("sync-reading-position");
const boundaryCue = document.getElementById("boundary-cue");
const boundaryCueLabel = document.getElementById("boundary-cue-label");
const boundaryCueMeter = document.getElementById("boundary-cue-meter");
const nodes = nodeFactory();
const storage = window.localStorage;
const readerUser = window.__READER_USER__ || "";

let preferences = readPreferences(storage);
let open = null;
let scenePanelNode = null;
let saveTimer = null;
let syncTimer = null;
let measureFrame = null;
let measureShouldSave = false;
let jumpPages = new Map();
let pageManuscript = null;
let readerItems = [];
let readerItemsLoaded = false;
let readerSettings = { sync_reading_position: false };
let positionWrite = Promise.resolve();
let editorContext = null;
let publication = null;
let publicationDirty = false;
let exporting = false;
let touchY = null;
let boundaryTimer = null;
const edgeGesture = boundaryGesture();
let searchMatches = [];

const MODE_TEXT = {
  focused: ["Focused", "Prose and bookmarks — nothing from any other service. Switch to Full view."],
  full: ["Full view", "With the Chronos scenes this section was written from. Switch to Focused."],
};

// A stable line near the top of the viewport is anchored to a manuscript block
// so a typeface or window-width change can still restore the same words.
const markerLine = () => Math.min(96, window.innerHeight / 3);
const home = () => `${BASE}/`;

function bookUrl(book) {
  return `${home()}?${new URLSearchParams({ book })}`;
}

function readerUrl(book, volume, section, block = null) {
  const query = { book, volume, section };
  if (block) query.block = block;
  return `${home()}?${new URLSearchParams(query)}`;
}

function words(count) {
  if (!Number.isFinite(count)) return "";
  return `${count.toLocaleString()} ${count === 1 ? "word" : "words"}`;
}

/** Join the parts of a meta line that are actually there. */
const meta = (...parts) => parts.filter(Boolean).join(" · ");

function percent(value) {
  return `${Math.round(value * 100)}%`;
}

function hideReaderChrome() {
  toolbar.hidden = true;
  progressRegion.hidden = true;
  open = null;
}

// -- shelf -------------------------------------------------------------------

function continueLink(book, position, label = "Continue reading") {
  return el("a", {
    class: "continue-link",
    href: readerUrl(book, position.volume, position.section),
  }, [
    el("span", { text: label }),
    el("span", { class: "continue-progress", text: percent(position.progress) }),
  ]);
}

function bookCard(row) {
  const saved = row.has_manuscript
    ? readPosition(storage, readerUser, row.book) : null;
  const furthest = saved && saved.furthest;
  const summary = row.has_manuscript
    ? `${row.volume_count} ${row.volume_count === 1 ? "volume" : "volumes"}`
    : "No manuscript yet";
  const heading = el("h2", { text: row.title || row.book });
  return el("article", { class: `card${row.has_manuscript ? "" : " inert"}` }, [
    row.has_manuscript
      ? el("a", { class: "card-link", href: bookUrl(row.book) }, [heading])
      : heading,
    el("p", { class: "card-sub", text: row.book }),
    el("p", { class: "card-meta", text: summary }),
    furthest ? continueLink(row.book, furthest) : null,
  ]);
}

function renderShelf(books) {
  hideReaderChrome();
  pageManuscript = null;
  document.title = "Logos — manuscripts";
  prunePositions(
    storage,
    readerUser,
    books.filter((book) => book.has_manuscript).map((book) => book.book),
  );
  fill(content, [
    el("div", { class: "page-heading" }, [
      el("p", { class: "eyebrow", text: "Read-only library" }),
      el("h1", { text: "Manuscripts" }),
      el("p", { class: "lead", text: "Choose a book to browse its volumes and sections." }),
    ]),
    books.length
      ? el("div", { class: "card-grid" }, books.map(bookCard))
      : el("p", { class: "empty", text: "No readable Chronos books are available." }),
  ]);
}

// -- book contents -----------------------------------------------------------

/**
 * The saved marks that still name sections this manuscript has.
 *
 * `last` says which volume to open and where to put the scroll; `furthest` is
 * what "Continue reading" points at. Either can outlive the other -- an edit
 * can delete the section you were last in without touching the one you got to
 * -- so they are located separately, and the book is only forgotten when
 * neither lands.
 */
function bookmarks(manuscript) {
  const saved = readPosition(storage, readerUser, manuscript.book);
  if (!saved) return null;
  const locate = (mark) => {
    const entry = mark && findSection(manuscript, mark.volume, mark.section);
    return entry ? { mark, entry } : null;
  };
  const last = locate(saved.last);
  const furthest = locate(saved.furthest);
  if (!last && !furthest) {
    forgetPosition(storage, readerUser, manuscript.book);
    return null;
  }
  return { last: last || furthest, furthest: furthest || last };
}

/**
 * The kind to print above a row's name, or null when it would say nothing.
 *
 * An untitled section is *named* for its kind already, and a row under a run
 * heading has just been told what kind it is -- unless the label carries a
 * number the heading does not.
 */
function sectionRow(manuscript, volume, section, marks) {
  const resume = marks && marks.furthest;
  const isResume = resume
    && resume.mark.volume === volume.id
    && resume.mark.section === section.id;
  // An untitled section is named for its kind already, so the label would only
  // say it twice. Nothing else in the outline names a kind: every row carries
  // its own, which is why a heading above a run of them has nothing to add.
  const kind = section.title ? sectionLabel(section) : null;
  const count = words(section.word_count);
  return el("li", { class: `section-row${isResume ? " resume" : ""}` }, [
    el("a", {
      class: "section-link",
      href: readerUrl(manuscript.book, volume.id, section.id),
    }, [
      el("span", { class: "section-name" }, [
        kind ? el("span", { class: "section-kind", text: kind }) : null,
        el("strong", { text: sectionName(section) }),
      ]),
      count ? el("span", { class: "section-stats", text: count }) : null,
      isResume
        ? el("span", {
            class: "resume-marker",
            text: `Continue here · ${percent(resume.mark.progress)}`,
          })
        : null,
    ]),
  ]);
}

function pagedSectionList(
  sections, initialPage, rowFactory, label, onPage, listClass = "section-list",
) {
  const list = el("ol", { class: listClass });
  if (sections.length <= SECTION_PAGE_SIZE) {
    fill(list, sections.map(rowFactory));
    onPage(0);
    return list;
  }

  let current = null;
  const status = el("span", { class: "page-range" });
  const previous = el("button", {
    class: "page-btn", type: "button", text: "← Previous",
    "aria-label": `Previous sections in ${label}`,
    onclick: () => turn(current.page - 1),
  });
  const next = el("button", {
    class: "page-btn", type: "button", text: "Next →",
    "aria-label": `Next sections in ${label}`,
    onclick: () => turn(current.page + 1),
  });
  const paint = (requested) => {
    current = sectionPage(sections, requested);
    fill(list, current.sections.map(rowFactory));
    previous.disabled = current.page === 0;
    next.disabled = current.page === current.pages - 1;
    status.textContent = `Sections ${current.start + 1}–${current.end} of ${current.total}`;
    onPage(current.page);
  };
  const turn = (page) => {
    paint(page);
    const first = list.querySelector("a");
    if (first) first.focus();
  };
  const pager = el("nav", { class: "section-pages", "aria-label": `Browse ${label}` }, [
    previous,
    status,
    next,
  ]);
  paint(initialPage);
  return el("div", { class: "section-window" }, [list, pager]);
}

function volumeCard(
  manuscript, volume, marks, expanded, searching, page, rememberPage, rememberOpen,
) {
  const summary = searching
    ? `${volume.sections.length} matching ${volume.sections.length === 1 ? "section" : "sections"}`
    : meta(
        `${volume.section_count} ${volume.section_count === 1 ? "section" : "sections"}`,
        words(volume.word_count),
      );
  // One argument on purpose: `Array.map` would otherwise hand the row builder
  // an index as its second.
  const row = (section) => sectionRow(manuscript, volume, section, marks);
  const sectionList = searching
    ? el("ol", { class: "section-list" }, volume.sections.map(row))
    : pagedSectionList(volume.sections, page, row, volume.title, rememberPage);
  return el("details", {
    class: "volume-card",
    open: expanded,
    ontoggle: (event) => rememberOpen(event.currentTarget.open),
  }, [
    el("summary", { class: "volume-summary" }, [
      el("span", { class: "volume-summary-copy" }, [
        el("span", { class: "eyebrow", text: `Volume ${volume.number}` }),
        el("strong", {
          class: "volume-title", role: "heading", "aria-level": "2", text: volume.title,
        }),
        volume.overview
          ? el("span", { class: "volume-overview", text: volume.overview }) : null,
      ]),
      el("span", {
        class: "volume-summary-meta",
        text: summary,
      }),
      el("span", { class: "twisty", "aria-hidden": "true" }),
    ]),
    volume.sections.length
      ? sectionList
      : el("p", { class: "volume-empty", text: "No sections yet." }),
  ]);
}

function outlineBrowser(manuscript, marks) {
  const total = sectionCount(manuscript.volumes);
  const list = el("div", { class: "volume-list" });
  // The volume that opens is the one you were last in, not the one you got
  // furthest into: after going back to re-read, the page should show you
  // where you are and leave "Continue reading" to offer the way forward.
  const here = marks && marks.last;
  const opened = defaultOpenVolume(manuscript, here && here.mark);
  const expanded = new Map(
    manuscript.volumes.map((volume) => [volume.id, volume.id === opened]),
  );
  const pages = new Map();
  for (const at of [marks && marks.furthest, here]) {
    if (at) {
      pages.set(
        at.entry.volume.id,
        pageForSection(at.entry.volume.sections, at.entry.section.id),
      );
    }
  }
  const status = el("p", { class: "outline-search-status muted", "aria-live": "polite" });

  const render = (query) => {
    const filtered = filterOutline(manuscript, query);
    const searching = Boolean(query.trim());
    const found = sectionCount(filtered);
    status.textContent = searching
      ? `${found} ${found === 1 ? "section" : "sections"} found`
      : "";
    fill(list, filtered.length
      ? filtered.map((volume) => volumeCard(
          manuscript,
          volume,
          marks,
          searching || expanded.get(volume.id),
          searching,
          pages.get(volume.id) || 0,
          (page) => pages.set(volume.id, page),
          (isOpen) => {
            if (!searching) expanded.set(volume.id, isOpen);
          },
        ))
      : [el("p", { class: "empty outline-empty", text: "No sections match your search." })]);
  };

  if (!total) {
    render("");
    return list;
  }
  const search = el("input", {
    id: "outline-search",
    class: "outline-search",
    type: "search",
    placeholder: "Title, chapter, type, or volume",
    autocomplete: "off",
    oninput: (event) => render(event.target.value),
  });
  render("");
  return el("div", { class: "outline-browser" }, [
    el("div", { class: "outline-search-row", role: "search" }, [
      el("label", { for: "outline-search", text: "Find a section" }),
      search,
      status,
    ]),
    list,
  ]);
}

function resumeCallout(manuscript, marks) {
  if (!marks || !marks.furthest) return null;
  const { mark, entry } = marks.furthest;
  return el("a", {
    class: "resume-callout",
    href: readerUrl(manuscript.book, mark.volume, mark.section),
  }, [
    el("span", { class: "resume-icon", "aria-hidden": "true", text: "▶" }),
    el("span", { class: "resume-copy" }, [
      el("strong", { text: "Continue reading" }),
      el("span", {
        text: `${entry.volume.title} · ${sectionName(entry.section)}`,
      }),
    ]),
    el("span", { class: "resume-percent", text: percent(mark.progress) }),
  ]);
}

function renderBook(manuscript, notice = null) {
  hideReaderChrome();
  pageManuscript = manuscript;
  const marks = bookmarks(manuscript);
  const totalSections = sectionCount(manuscript.volumes);
  document.title = `${manuscript.title || manuscript.book} — Logos`;
  fill(content, [
    el("div", { class: "book-heading" }, [
      el("a", { class: "back-link", href: home(), text: "← Manuscripts" }),
      el("p", { class: "eyebrow", text: "Book contents" }),
      el("h1", { text: manuscript.title || manuscript.book }),
      manuscript.overview ? el("p", { class: "lead book-overview", text: manuscript.overview }) : null,
      el("p", {
        class: "book-meta",
        text: meta(
          `${manuscript.volume_count} ${manuscript.volume_count === 1 ? "volume" : "volumes"}`,
          `${totalSections} ${totalSections === 1 ? "section" : "sections"}`,
          words(manuscript.word_count),
        ),
      }),
      manuscript.volumes.length ? el("div", { class: "book-actions" }, [
        el("button", { class: "btn ghost", type: "button", text: "Search series", onclick: openSearch }),
        el("button", { class: "btn ghost", type: "button", text: "Bookmarks", onclick: () => openBookmarks().catch((error) => showTransientError(error.message)) }),
        el("button", { class: "btn ghost", type: "button", text: "Publish series", onclick: openPublication }),
      ]) : null,
    ]),
    notice ? el("p", { class: "reader-notice", role: "status", text: notice }) : null,
    resumeCallout(manuscript, marks),
    manuscript.volumes.length
      ? outlineBrowser(manuscript, marks)
      : el("p", { class: "empty", text: "This book has no manuscript volumes yet." }),
  ]);
}

// -- section reader ----------------------------------------------------------

function prose(section) {
  try {
    return el("div", { class: "prose" }, [renderDocument(section.document, nodes)]);
  } catch (error) {
    if (!(error instanceof RenderError)) throw error;
    return el("div", { class: "prose" }, [
      el("p", {
        class: "prose-error",
        text: "This section uses features this reader does not know yet."
          + " Read it through the API until Logos is updated.",
      }),
    ]);
  }
}

function scenePanel(section) {
  scenePanelNode = null;
  if (!(section.event_ids || []).length) return null;
  scenePanelNode = el("section", { class: "scenes" }, [
    el("p", { class: "scenes-status", text: "Loading linked scenes…" }),
  ]);
  return scenePanelNode;
}

function insightPanel(section) {
  return el("aside", {
    class: "insights",
    "aria-label": `Notes and context for ${sectionName(section)}`,
  }, [scenePanel(section), el("div", { id: "personal-panel", class: "personal-panel" })]);
}

function pagerLink(entry, direction) {
  if (!entry) return el("span");
  const backwards = direction === "previous";
  return el("a", {
    href: readerUrl(open.manuscript.book, entry.volume.id, entry.section.id),
    class: `pager-link ${direction}`,
    "aria-label": `${backwards ? "Previous" : "Next"}: ${sectionName(entry.section)}`,
  }, [
    el("span", { class: "pager-direction", text: backwards ? "← Previous" : "Next →" }),
    el("strong", { text: sectionName(entry.section) }),
    el("span", { class: "pager-volume", text: entry.volume.title }),
  ]);
}

function sectionPager(manuscript, volume, section) {
  const adjacent = sectionNeighbours(manuscript, volume.id, section.id);
  return el("nav", { class: "section-pager", "aria-label": "Adjacent sections" }, [
    pagerLink(adjacent.previous, "previous"),
    pagerLink(adjacent.next, "next"),
  ]);
}

function renderReader(manuscript, entry, section) {
  pageManuscript = manuscript;
  toolbar.hidden = false;
  progressRegion.hidden = false;
  document.title = `${sectionName(section)} — ${manuscript.title || manuscript.book}`;
  const proseNode = prose(section);
  const article = el("article", { class: "section reading-section" }, [
    el("header", { class: "section-head" }, [
      el("p", {
        class: "eyebrow",
        text: `Volume ${entry.volume.number} · ${entry.volume.title}`,
      }),
      el("h1", { text: sectionName(section) }),
      el("p", {
        class: "section-meta",
        text: meta(sectionLabel(section), words(section.word_count)),
      }),
    ]),
    el("div", { class: "section-body" }, [proseNode, insightPanel(section)]),
  ]);
  open.article = article;
  open.prose = proseNode;
  fill(content, [
    el("a", {
      class: "back-link",
      href: bookUrl(manuscript.book),
      text: `← Contents for ${manuscript.title || manuscript.book}`,
    }),
    article,
    sectionPager(manuscript, entry.volume, section),
  ]);
}

// -- jump to section ---------------------------------------------------------

function jumpSectionLink(volume, section) {
  const current = open.volume.id === volume.id && open.section.id === section.id;
  const kind = section.title ? sectionLabel(section) : null;
  return el("li", {}, [
    el("a", {
      class: `jump-section${current ? " current" : ""}`,
      href: readerUrl(open.manuscript.book, volume.id, section.id),
      ...(current ? { "aria-current": "page" } : {}),
    }, [
      el("span", { text: sectionName(section) }),
      kind ? el("span", { class: "jump-kind", text: kind }) : null,
    ]),
  ]);
}

function jumpVolume(volume, searching) {
  const row = (section) => jumpSectionLink(volume, section);
  const sections = searching
    ? el("ol", { class: "jump-section-list" }, volume.sections.map(row))
    : pagedSectionList(
        volume.sections,
        jumpPages.get(volume.id) || 0,
        row,
        volume.title,
        (page) => jumpPages.set(volume.id, page),
        "jump-section-list",
      );
  return el("section", { class: "jump-volume" }, [
    el("h3", { text: `Volume ${volume.number} · ${volume.title}` }),
    sections,
  ]);
}

function renderJumpResults(query) {
  if (!open) return;
  const volumes = filterOutline(open.manuscript, query);
  const searching = Boolean(query.trim());
  const found = sectionCount(volumes);
  jumpStatus.textContent = `${found} ${found === 1 ? "section" : "sections"}`;
  fill(jumpResults, volumes.length
    ? volumes.map((volume) => jumpVolume(volume, searching))
    : [el("p", { class: "empty jump-empty", text: "No sections match your search." })]);
}

function openJump() {
  if (!open) return;
  jumpPages = new Map([[
    open.volume.id,
    pageForSection(open.volume.sections, open.section.id),
  ]]);
  jumpSearch.value = "";
  renderJumpResults("");
  jumpDialog.showModal();
  jumpSearch.focus();
  const current = jumpResults.querySelector('[aria-current="page"]');
  if (current) current.scrollIntoView({ block: "nearest" });
}

// -- full view ---------------------------------------------------------------

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
  if (!scenePanelNode) return;
  fill(scenePanelNode, [
    el("h2", { text: "Linked scenes" }),
    el("ul", { class: "scene-list" }, payload.scenes.map(sceneCard)),
  ]);
}

function sceneLoadFailed(error) {
  if (!scenePanelNode) return;
  const detail = error instanceof ApiError && error.status === 403
    ? "You may read this prose but not the timeline behind it."
    : "The linked scenes could not be loaded.";
  fill(scenePanelNode, [el("p", { class: "scenes-status", text: detail })]);
}

async function loadScenes() {
  if (!open || open.scenesLoaded || !scenePanelNode) return;
  open.scenesLoaded = true;
  try {
    fillScenes(await api.scenes(open.manuscript.book, open.volume.id, open.section.id));
  } catch (error) {
    open.scenesLoaded = false;
    sceneLoadFailed(error);
  }
}

// -- private notes, checklists and bookmarks --------------------------------

async function loadReaderData() {
  if (!pageManuscript || readerItemsLoaded) return;
  const payload = await api.readerItems(pageManuscript.book);
  readerItems = payload.items;
  readerItemsLoaded = true;
  refreshReaderData();
}

function currentReaderData() {
  if (!open) return { notes: [], bookmarks: [], sectionChecklist: [], bookChecklist: [] };
  return dataForSection(readerItems, open.volume.id, open.section.id);
}

function refreshReaderData() {
  if (!open) return;
  decorateParagraphs();
  renderPersonalPanel();
  if (bookmarksDialog.open) renderBookmarks();
}

// A ribbon, not a star: filled versus hollow has to be legible at a glance and
// without relying on colour alone, which two sizes of the same star never were.
const BOOKMARK_PATH = "M4 2.6h8a1.4 1.4 0 0 1 1.4 1.4v13.4L8 14.2 2.6 17.4V4A1.4 1.4 0 0 1 4 2.6z";

function bookmarkIcon(saved) {
  return svgEl(
    "svg",
    { viewBox: "0 0 16 20", width: "15", height: "19", "aria-hidden": "true",
      focusable: "false" },
    [svgEl("path", {
      d: BOOKMARK_PATH,
      fill: saved ? "currentColor" : "none",
      stroke: "currentColor",
      "stroke-width": saved ? "0" : "1.7",
      "stroke-linejoin": "round",
    })],
  );
}

function decorateParagraphs() {
  if (!open || !open.prose) return;
  for (const old of open.prose.querySelectorAll(".reader-block-tools")) old.remove();
  const data = currentReaderData();
  for (const block of open.prose.querySelectorAll('[data-block-type="paragraph"]')) {
    const blockId = block.dataset.blockId;
    const bookmark = bookmarkAt(data.bookmarks, open.volume.id, open.section.id, blockId);
    const noteCount = data.notes.filter((note) => note.block === blockId).length;
    const tools = el("span", { class: "reader-block-tools" }, [
      el("button", {
        class: `block-tool bookmark-tool${bookmark ? " active" : ""}`,
        type: "button",
        title: bookmark ? "Remove bookmark" : "Bookmark paragraph",
        "aria-label": bookmark ? "Remove bookmark" : "Bookmark paragraph",
        "aria-pressed": bookmark ? "true" : "false",
        onclick: () => toggleBookmark(blockId, bookmark),
      }, [bookmarkIcon(Boolean(bookmark))]),
      el("button", {
        class: `block-tool note-tool${noteCount ? " active" : ""}`,
        type: "button",
        text: noteCount ? `✎${noteCount}` : "✎",
        title: "Add a private note",
        "aria-label": "Add a private note to this paragraph",
        onclick: () => openItemEditor({ kind: "note", block: blockId }),
      }),
    ]);
    // The rail stays inside the paragraph so it keeps the paragraph's own
    // positioning context and every scroll measurement still lines up. CSS
    // makes it unselectable, which is what keeps the glyphs out of copied prose.
    block.appendChild(tools);
  }
}

async function toggleBookmark(block, held) {
  try {
    if (held) {
      await api.deleteReaderItem(pageManuscript.book, held.id, held.rev);
      readerItems = removeItem(readerItems, held.id);
    } else {
      const saved = await api.createReaderItem(pageManuscript.book, {
        kind: "bookmark",
        volume: open.volume.id,
        section: open.section.id,
        block,
        text: "",
      });
      readerItems = replaceItem(readerItems, saved);
    }
    refreshReaderData();
  } catch (error) {
    showTransientError(error.message || "The bookmark could not be saved.");
  }
}

function checklist(title, scope, items) {
  const rows = items.map((item) => el("li", { class: "check-row" }, [
    el("input", {
      type: "checkbox",
      ...(item.done ? { checked: true } : {}),
      "aria-label": `${item.done ? "Reopen" : "Complete"} ${item.text}`,
      onchange: (event) => updateChecklist(item, { done: event.target.checked }),
    }),
    el("button", {
      class: item.done ? "check-text done" : "check-text",
      type: "button",
      text: item.text,
      onclick: () => openItemEditor({ kind: "checklist", scope, item }),
    }),
  ]));
  return el("section", { class: "private-group" }, [
    el("div", { class: "private-heading" }, [
      el("h2", { text: title }),
      el("button", {
        class: "mini-action", type: "button", text: "+ Add",
        onclick: () => openItemEditor({ kind: "checklist", scope }),
      }),
    ]),
    rows.length
      ? el("ul", { class: "check-list" }, rows)
      : el("p", { class: "private-empty", text: "No items." }),
  ]);
}

function noteCard(note) {
  return el("button", {
    class: `note-card${note.available === false ? " unavailable" : ""}`,
    type: "button",
    onclick: () => openItemEditor({ kind: "note", block: note.block, item: note }),
  }, [
    el("span", { class: "note-copy", text: note.text }),
    el("span", { class: "note-anchor", text: note.available === false
      ? "Paragraph no longer exists" : note.excerpt || "Paragraph note" }),
  ]);
}

function renderPersonalPanel() {
  const panel = document.getElementById("personal-panel");
  if (!panel || !readerItemsLoaded) return;
  const data = currentReaderData();
  fill(panel, [
    checklist("Series checklist", "book", data.bookChecklist),
    checklist("Section checklist", "section", data.sectionChecklist),
    el("section", { class: "private-group" }, [
      el("div", { class: "private-heading" }, [el("h2", { text: "Paragraph notes" })]),
      data.notes.length
        ? el("div", { class: "note-list" }, data.notes.map(noteCard))
        : el("p", { class: "private-empty", text: "Use the pencil beside a paragraph to add a note." }),
    ]),
  ]);
}

async function updateChecklist(item, patch) {
  try {
    const saved = await api.updateReaderItem(
      pageManuscript.book, item.id, patch, item.rev,
    );
    readerItems = replaceItem(readerItems, saved);
    refreshReaderData();
  } catch (error) {
    showTransientError(error.message || "The checklist could not be updated.");
    await reloadReaderData();
  }
}

function openItemEditor(context) {
  if (bookmarksDialog.open) bookmarksDialog.close();
  editorContext = context;
  const editing = context.item || null;
  const names = { note: "note", checklist: "checklist item", bookmark: "bookmark label" };
  itemEditorTitle.textContent = `${editing ? "Edit" : "Add"} ${names[context.kind]}`;
  itemEditorText.value = editing ? editing.text : "";
  itemEditorText.maxLength = context.kind === "note" ? 10000 : 1000;
  itemEditorDelete.hidden = !editing;
  itemEditorError.textContent = "";
  itemEditor.showModal();
  itemEditorText.focus();
}

async function saveEditorItem() {
  const context = editorContext;
  if (!context || !open) return;
  const text = itemEditorText.value.trim();
  const editing = context.item || null;
  let saved;
  if (editing) {
    saved = await api.updateReaderItem(
      pageManuscript.book, editing.id, { text }, editing.rev,
    );
  } else if (context.kind === "note") {
    saved = await api.createReaderItem(pageManuscript.book, {
      kind: "note", volume: open.volume.id, section: open.section.id,
      block: context.block, text,
    });
  } else {
    saved = await api.createReaderItem(pageManuscript.book, {
      kind: "checklist", scope: context.scope, text, done: false,
      ...(context.scope === "section"
        ? { volume: open.volume.id, section: open.section.id } : {}),
    });
  }
  readerItems = replaceItem(readerItems, saved);
  itemEditor.close();
  refreshReaderData();
}

async function deleteEditorItem() {
  const item = editorContext && editorContext.item;
  if (!item) return;
  try {
    await api.deleteReaderItem(pageManuscript.book, item.id, item.rev);
    readerItems = removeItem(readerItems, item.id);
    itemEditor.close();
    refreshReaderData();
  } catch (error) {
    itemEditorError.textContent = error.message || "The item could not be deleted.";
  }
}

async function reloadReaderData() {
  readerItemsLoaded = false;
  await loadReaderData();
}

function showTransientError(message) {
  const notice = el("p", { class: "reader-toast", role: "alert", text: message });
  document.body.appendChild(notice);
  window.setTimeout(() => notice.remove(), 3500);
}

// -- bookmarks and manuscript search ---------------------------------------

function renderBookmarks() {
  const items = bookmarkItems(readerItems);
  bookmarksStatus.textContent = `${items.length} ${items.length === 1 ? "bookmark" : "bookmarks"}`;
  fill(bookmarksResults, items.length ? items.map((item) => {
    const entry = pageManuscript && findSection(pageManuscript, item.volume, item.section);
    const label = item.text || item.excerpt || "Bookmarked paragraph";
    return el("div", { class: "bookmark-row" }, [
      item.available !== false && entry
        ? el("a", {
            href: readerUrl(pageManuscript.book, item.volume, item.section, item.block),
          }, [
            el("strong", { text: label }),
            el("span", { text: `${entry.volume.title} · ${sectionName(entry.section)}` }),
          ])
        : el("span", {}, [
            el("strong", { text: label }),
            el("span", { text: "Paragraph no longer exists" }),
          ]),
      el("span", { class: "bookmark-actions" }, [
        el("button", {
          class: "icon-btn", type: "button", text: "✎", title: "Edit bookmark label",
          "aria-label": `Edit bookmark ${label}`,
          onclick: () => openItemEditor({ kind: "bookmark", item }),
        }),
        el("button", {
          class: "icon-btn", type: "button", text: "×", title: "Delete bookmark",
          "aria-label": `Delete bookmark ${label}`,
          onclick: async () => {
            await api.deleteReaderItem(pageManuscript.book, item.id, item.rev);
            readerItems = removeItem(readerItems, item.id);
            renderBookmarks();
            refreshReaderData();
          },
        }),
      ]),
    ]);
  }) : [el("p", { class: "empty jump-empty", text: "No bookmarks in this series." })]);
}

async function openBookmarks() {
  if (!pageManuscript) return;
  await loadReaderData();
  renderBookmarks();
  bookmarksDialog.showModal();
}

function openSearch() {
  if (!pageManuscript) return;
  searchStatus.textContent = "";
  fill(searchResults, []);
  searchMatches = [];
  searchDialog.showModal();
  searchInput.focus();
}

async function runSearch(offset = 0) {
  const query = searchInput.value.trim();
  if (!query || !pageManuscript) return;
  searchStatus.textContent = "Searching…";
  try {
    const payload = await api.search(pageManuscript.book, query, offset);
    searchMatches = offset ? [...searchMatches, ...payload.results] : payload.results;
    searchStatus.textContent = `${payload.total} ${payload.total === 1 ? "section" : "sections"} found`;
    const rows = searchMatches.map((result) =>
      el("a", {
        class: "search-result",
        href: readerUrl(payload.book, result.volume, result.section, result.block),
      }, [
        el("span", { class: "search-result-place", text: `Volume ${result.volume_number} · ${result.volume_title} · ${result.section_label}` }),
        el("strong", { text: result.section_title }),
        result.snippet ? el("span", { class: "search-snippet", text: result.snippet }) : null,
      ]));
    if (payload.next_offset !== null) rows.push(el("button", {
      class: "btn ghost search-more", type: "button", text: "More results",
      onclick: () => runSearch(payload.next_offset),
    }));
    fill(searchResults, rows.length
      ? rows : [el("p", { class: "empty jump-empty", text: "No manuscript text matches." })]);
  } catch (error) {
    searchStatus.textContent = error.message || "Search failed.";
  }
}

// -- publication ------------------------------------------------------------

const PUBLICATION_FIELDS = [
  ["title", "Title"], ["subtitle", "Subtitle"], ["author", "Author"],
  ["language", "Language"], ["publisher", "Publisher"],
  ["copyright", "Copyright"],
];

function publicationField([name, label]) {
  return el("label", { class: "publication-field" }, [
    el("span", { text: label }),
    el("input", {
      name, value: publication[name] || "", maxlength: "500",
      oninput: () => { publicationDirty = true; },
      ...(name === "title" || name === "language" ? { required: true } : {}),
      ...(pageManuscript.permissions.write ? {} : { disabled: true }),
    }),
  ]);
}

async function openPublication() {
  if (!pageManuscript) return;
  publicationError.textContent = "Loading publication details…";
  publicationDialog.showModal();
  try {
    publication = await api.publication(pageManuscript.book);
    publicationDirty = false;
    fill(publicationFields, PUBLICATION_FIELDS.map(publicationField));
    const writable = pageManuscript.permissions.write;
    publicationCover.disabled = !writable;
    publicationForm.querySelector('button[type="submit"]').hidden = !writable;
    coverDelete.hidden = !writable || !publication.has_cover;
    publicationError.textContent = publication.has_cover ? "A cover image is set." : "";
  } catch (error) {
    publicationError.textContent = error.message || "Publication details could not be loaded.";
  }
}

async function savePublication() {
  const metadata = Object.fromEntries(
    PUBLICATION_FIELDS.map(([name]) => [name, publicationForm.elements[name].value]),
  );
  publication = publication.rev
    ? await api.updatePublication(pageManuscript.book, metadata, publication.rev)
    : await api.createPublication(pageManuscript.book, metadata);
  const file = publicationCover.files[0];
  if (file) {
    await api.saveCover(pageManuscript.book, await file.arrayBuffer());
    publication.has_cover = true;
    publicationCover.value = "";
  }
  coverDelete.hidden = !publication.has_cover;
  publicationDirty = false;
  publicationError.textContent = "Publication details saved.";
}

async function removeCover() {
  try {
    await api.deleteCover(pageManuscript.book);
    publication.has_cover = false;
    coverDelete.hidden = true;
    publicationError.textContent = "Cover removed.";
  } catch (error) {
    publicationError.textContent = error.message || "The cover could not be removed.";
  }
}

const PDF_POLL_MS = 2000;
const PDF_GIVE_UP_MS = 15 * 60 * 1000;

/** Start the render, then ask for it until the server hands it over. */
async function renderPdf(book) {
  const { job } = await api.startPdf(book);
  const deadline = Date.now() + PDF_GIVE_UP_MS;
  for (let attempt = 1; Date.now() < deadline; attempt += 1) {
    await new Promise((resume) => window.setTimeout(resume, PDF_POLL_MS));
    const exported = await api.collectPdf(book, job);
    if (exported) return exported;
    publicationError.textContent =
      `Typesetting the series… (${attempt * (PDF_POLL_MS / 1000)}s)`;
  }
  throw new Error("The PDF is taking longer than expected. Try again later.");
}

async function downloadPublication(format) {
  if (!pageManuscript || !publication || exporting) return;
  // A whole-series PDF is minutes of work and gigabytes of peak memory on the
  // server. An impatient second click must not start a second one.
  exporting = true;
  for (const button of [exportEpubButton, exportPdfButton]) button.disabled = true;
  try {
    if (pageManuscript.permissions.write && publicationDirty) await savePublication();
    publicationError.textContent = `Creating ${format.toUpperCase()}…`;
    const exported = format === "epub"
      ? await api.exportEpub(pageManuscript.book)
      : await renderPdf(pageManuscript.book);
    const link = document.createElement("a");
    const url = URL.createObjectURL(exported.blob);
    link.href = url;
    link.download = exported.filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    publicationError.textContent = "Download ready.";
  } finally {
    exporting = false;
    for (const button of [exportEpubButton, exportPdfButton]) button.disabled = false;
  }
}

// -- reading position and progress ------------------------------------------

function readingGeometry() {
  const article = open.article.getBoundingClientRect();
  const prose = open.prose.getBoundingClientRect();
  const top = article.top + window.scrollY;
  return {
    top,
    height: prose.bottom + window.scrollY - top,
    scrollY: window.scrollY,
    viewportHeight: window.innerHeight,
  };
}

function paintProgress(value) {
  const rounded = Math.round(value * 100);
  progressMeter.value = rounded;
  progressValue.textContent = `${rounded}%`;
}

function blockSnapshot() {
  const marker = window.scrollY + markerLine();
  const blocks = Array.from(open.prose.querySelectorAll("[data-block-id]"))
    .map((node) => ({
      id: node.dataset.blockId,
      top: node.getBoundingClientRect().top + window.scrollY,
    }));
  return blockAnchor(blocks, marker);
}

function savePosition() {
  if (!open || open.restoring) return;
  if (saveTimer !== null) window.clearTimeout(saveTimer);
  saveTimer = null;
  const book = open.manuscript.book;
  const spot = {
    volume: open.volume.id,
    section: open.section.id,
    ...blockSnapshot(),
    progress: sectionProgress(readingGeometry()),
  };
  // Where you are always moves; how far you got only moves forward.
  const held = readPosition(storage, readerUser, book);
  const saved = writePosition(storage, readerUser, book, spot,
    sectionAhead(open.manuscript, spot, held && held.furthest));
  if (readerSettings.sync_reading_position && saved) queueSync(book);
}

// The local mark is written every 200ms of scrolling because it is free. The
// server copy is not: it rides a second timer so a minute of reading costs one
// request rather than three hundred, and `flushSync` covers leaving the page
// before that timer fires.
function queueSync(book) {
  if (syncTimer !== null) window.clearTimeout(syncTimer);
  syncTimer = window.setTimeout(() => flushSync(book), 1000);
}

function flushSync(book) {
  if (syncTimer !== null) window.clearTimeout(syncTimer);
  syncTimer = null;
  const mark = readPosition(storage, readerUser, book);
  if (!mark || !readerSettings.sync_reading_position) return;
  positionWrite = positionWrite
    .then(() => api.saveReadingPosition(book, mark))
    .then((payload) => storePosition(storage, readerUser, book, payload.position))
    .catch(() => null);
}

function queueSave() {
  if (saveTimer !== null) window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(savePosition, 200);
}

/** Leaving the page: take the local mark, then send it without waiting. */
function leaving() {
  savePosition();
  if (open && readerSettings.sync_reading_position) {
    flushSync(open.manuscript.book);
  }
}

function measure(save = true) {
  if (!open) return;
  paintProgress(sectionProgress(readingGeometry()));
  if (save && !open.restoring) queueSave();
}

function scheduleMeasure(save = true) {
  measureShouldSave ||= save;
  if (measureFrame !== null) return;
  measureFrame = window.requestAnimationFrame(() => {
    measureFrame = null;
    const shouldSave = measureShouldSave;
    measureShouldSave = false;
    measure(shouldSave);
  });
}

const nextFrame = () => new Promise((resolve) => window.requestAnimationFrame(resolve));

function findBlock(id) {
  if (!id) return null;
  return Array.from(open.prose.querySelectorAll("[data-block-id]"))
    .find((node) => node.dataset.blockId === id) || null;
}

async function restorePosition(position, requestedBlock = null) {
  open.restoring = true;
  await nextFrame();
  await nextFrame();
  const explicit = requestedBlock && findBlock(requestedBlock);
  const block = explicit || (position && findBlock(position.block));
  const target = block
    ? scrollForAnchor(
        block.getBoundingClientRect().top + window.scrollY,
        explicit ? 0 : position.offset,
        markerLine(),
      )
    : scrollForProgress(readingGeometry(), position ? position.progress : 0);
  window.scrollTo({ top: Math.max(0, target), behavior: "auto" });
  await nextFrame();
  open.restoring = false;
  if (explicit) {
    explicit.classList.add("target-block");
    explicit.setAttribute("tabindex", "-1");
    explicit.focus({ preventScroll: true });
  }
  measure(true);
}

async function syncStoredPosition(book) {
  if (!readerSettings.sync_reading_position) return readPosition(storage, readerUser, book);
  const local = readPosition(storage, readerUser, book);
  try {
    const payload = local
      ? await api.saveReadingPosition(book, local)
      : await api.readingPosition(book);
    return storePosition(storage, readerUser, book, payload.position);
  } catch (_error) {
    return local;
  }
}

// -- deliberate navigation beyond a section boundary -----------------------

function paintBoundary(state) {
  boundaryCue.hidden = !state.direction || state.progress === 0;
  if (boundaryCue.hidden) return;
  boundaryCueLabel.textContent = state.direction === "next"
    ? "Keep scrolling for next section" : "Keep scrolling for previous section";
  boundaryCueMeter.value = Math.round(state.progress * 100);
}

function boundaryInput(delta) {
  if (!open || open.restoring || document.querySelector("dialog[open]")) return;
  const doc = document.documentElement;
  const state = edgeGesture.push({
    delta,
    atStart: window.scrollY <= 1,
    atEnd: window.scrollY + window.innerHeight >= doc.scrollHeight - 2,
    now: performance.now(),
  });
  paintBoundary(state);
  if (boundaryTimer !== null) window.clearTimeout(boundaryTimer);
  boundaryTimer = window.setTimeout(() => {
    boundaryTimer = null;
    paintBoundary(edgeGesture.reset());
  }, 700);
  if (state.trigger) navigateBoundary(state.trigger);
}

function navigateBoundary(direction) {
  if (!open || open.navigating) return;
  const adjacent = sectionNeighbours(
    open.manuscript, open.volume.id, open.section.id,
  )[direction];
  if (!adjacent) {
    paintBoundary(edgeGesture.reset());
    return;
  }
  open.navigating = true;
  savePosition();
  document.body.classList.add(`navigating-${direction}`);
  const url = readerUrl(
    open.manuscript.book, adjacent.volume.id, adjacent.section.id,
  );
  const delay = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 140;
  window.setTimeout(() => window.location.assign(url), delay);
}

// -- preferences and entry ---------------------------------------------------

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
  preferences = writePreferences(storage, patch);
  applyPreferences();
  scheduleMeasure(false);
}

function wire() {
  modeButton.addEventListener("click", () => {
    update({ mode: otherMode(preferences.mode) });
    if (showsChronos(preferences)) loadScenes().then(() => scheduleMeasure(false));
  });
  for (const field of DISPLAY_FIELDS) {
    document.getElementById(`display-${field}`)
      .addEventListener("change", (event) => update({ [field]: event.target.value }));
  }
  document.getElementById("display-reset")
    .addEventListener("click", () => update(resetDisplay(preferences)));
  document.getElementById("settings-open")
    .addEventListener("click", () => settings.showModal());
  syncControl.addEventListener("change", async (event) => {
    event.target.disabled = true;
    try {
      readerSettings = await api.saveReaderSettings({
        sync_reading_position: event.target.checked,
      });
      window.location.reload();
    } catch (error) {
      event.target.checked = readerSettings.sync_reading_position;
      event.target.disabled = false;
      showTransientError(error.message || "The sync setting could not be saved.");
    }
  });
  jumpButton.addEventListener("click", openJump);
  jumpSearch.addEventListener("input", (event) => renderJumpResults(event.target.value));
  searchButton.addEventListener("click", openSearch);
  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    runSearch();
  });
  bookmarksButton.addEventListener("click", () => openBookmarks().catch(
    (error) => showTransientError(error.message || "Bookmarks could not be loaded."),
  ));
  document.getElementById("item-editor-close").addEventListener("click", () => itemEditor.close());
  itemEditorForm.addEventListener("submit", (event) => {
    event.preventDefault();
    itemEditorError.textContent = "";
    saveEditorItem().catch((error) => {
      itemEditorError.textContent = error.message || "The item could not be saved.";
    });
  });
  itemEditorDelete.addEventListener("click", deleteEditorItem);
  document.getElementById("publication-close").addEventListener("click", () => publicationDialog.close());
  publicationForm.addEventListener("submit", (event) => {
    event.preventDefault();
    publicationError.textContent = "Saving…";
    savePublication().catch((error) => {
      publicationError.textContent = error.message || "Publication details could not be saved.";
    });
  });
  coverDelete.addEventListener("click", removeCover);
  publicationCover.addEventListener("change", () => { publicationDirty = true; });
  exportEpubButton.addEventListener("click", () => {
    downloadPublication("epub").catch((error) => {
      publicationError.textContent = error.message || "The EPUB could not be created.";
    });
  });
  exportPdfButton.addEventListener("click", () => {
    downloadPublication("pdf").catch((error) => {
      publicationError.textContent = error.message || "The PDF could not be created.";
    });
  });
  window.addEventListener("scroll", () => scheduleMeasure(), { passive: true });
  window.addEventListener("wheel", (event) => boundaryInput(event.deltaY), { passive: true });
  window.addEventListener("touchstart", (event) => {
    touchY = event.touches.length === 1 ? event.touches[0].clientY : null;
  }, { passive: true });
  window.addEventListener("touchmove", (event) => {
    if (touchY === null || event.touches.length !== 1) return;
    const next = event.touches[0].clientY;
    boundaryInput(touchY - next);
    touchY = next;
  }, { passive: true });
  window.addEventListener("touchend", () => { touchY = null; }, { passive: true });
  window.addEventListener("resize", () => scheduleMeasure(false));
  window.addEventListener("pagehide", leaving);
  // A phone that backgrounds the tab and kills it later may never fire
  // `pagehide`, and "closes their browser" is the whole point of the mark.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") leaving();
  });
  document.addEventListener("prefs:fontscale", () => scheduleMeasure(false));
}

function showFailure(error) {
  if (error instanceof ApiError && error.status === 403) {
    const book = new URLSearchParams(window.location.search).get("book");
    if (book) forgetPosition(storage, readerUser, book);
  }
  hideReaderChrome();
  fill(content, [
    el("div", { class: "page-heading" }, [
      el("p", { class: "eyebrow", text: "Logos" }),
      el("h1", { text: "This manuscript could not be opened" }),
      el("p", { class: "lead", text: error.message || "Something went wrong." }),
      el("a", { class: "back-link", href: home(), text: "← Manuscripts" }),
    ]),
  ]);
}

async function openSection(manuscript, entry) {
  const section = await api.section(
    manuscript.book, entry.volume.id, entry.section.id,
  );
  open = {
    manuscript,
    volume: entry.volume,
    section,
    article: null,
    prose: null,
    scenesLoaded: false,
    restoring: true,
    navigating: false,
  };
  readerItems = [];
  readerItemsLoaded = false;
  renderReader(manuscript, entry, section);
  if (showsChronos(preferences)) await loadScenes();
  try {
    await loadReaderData();
  } catch (error) {
    showTransientError(error.message || "Private reader data could not be loaded.");
  }
  // Only the spot you actually left carries an anchor, and only if it is in
  // this section: opening any other section starts it at the top.
  const spot = (readPosition(storage, readerUser, manuscript.book) || {}).last;
  const here = spot && spot.volume === entry.volume.id
    && spot.section === section.id ? spot : null;
  const requestedBlock = new URLSearchParams(window.location.search).get("block");
  await restorePosition(here, requestedBlock);
}

async function start() {
  if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
  wire();
  applyPreferences();
  try {
    readerSettings = await api.readerSettings();
  } catch (_error) {
    readerSettings = { sync_reading_position: false };
  }
  syncControl.checked = readerSettings.sync_reading_position;
  const query = new URLSearchParams(window.location.search);
  const book = query.get("book");
  if (!book) {
    const books = (await api.books()).books;
    if (readerSettings.sync_reading_position) {
      await Promise.all(books.filter((row) => row.has_manuscript)
        .map((row) => syncStoredPosition(row.book)));
    }
    renderShelf(books);
    return;
  }

  const manuscript = await api.manuscript(book);
  await syncStoredPosition(book);
  const volume = query.get("volume");
  const section = query.get("section");
  if (!volume || !section) {
    renderBook(manuscript);
    return;
  }

  const entry = findSection(manuscript, volume, section);
  if (!entry) {
    // `bookmarks` drops whichever marks no longer land, so a link to a deleted
    // section needs no cleanup here beyond showing the outline again.
    renderBook(manuscript, "That section is no longer available. Choose another section.");
    return;
  }
  await openSection(manuscript, entry);
}

start().catch(showFailure);
