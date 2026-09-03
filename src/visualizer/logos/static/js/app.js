// Logos' three-page reader: manuscript shelf, book contents, and one section.
// Navigation uses ordinary links and full page loads so bookmarks, new tabs,
// and the browser's back button work without a client-side router.

import { ApiError, BASE, api } from "./api.js";
import { el, fill, nodeFactory } from "./dom.js";
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
const nodes = nodeFactory();
const storage = window.localStorage;
const readerUser = window.__READER_USER__ || "";

let preferences = readPreferences(storage);
let open = null;
let scenePanelNode = null;
let saveTimer = null;
let measureFrame = null;
let measureShouldSave = false;
let jumpPages = new Map();

const MODE_TEXT = {
  focused: ["Focused", "Prose alone — nothing from any other service. Switch to Full view."],
  full: ["Full view", "With the Chronos scenes this section was written from. Switch to Focused."],
};

// A stable line near the top of the viewport is anchored to a manuscript block
// so a typeface or window-width change can still restore the same words.
const markerLine = () => Math.min(96, window.innerHeight / 3);
const home = () => `${BASE}/`;

function bookUrl(book) {
  return `${home()}?${new URLSearchParams({ book })}`;
}

function readerUrl(book, volume, section) {
  return `${home()}?${new URLSearchParams({ book, volume, section })}`;
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
  scenePanelNode = el("aside", {
    class: "scenes",
    "aria-label": `Chronos scenes behind ${sectionName(section)}`,
  }, [el("p", { class: "scenes-status", text: "Loading linked scenes…" })]);
  return scenePanelNode;
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
    el("div", { class: "section-body" }, [proseNode, scenePanel(section)]),
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
  writePosition(storage, readerUser, book, spot,
    sectionAhead(open.manuscript, spot, held && held.furthest));
}

function queueSave() {
  if (saveTimer !== null) window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(savePosition, 200);
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

async function restorePosition(position) {
  open.restoring = true;
  await nextFrame();
  await nextFrame();
  const block = position && findBlock(position.block);
  const target = block
    ? scrollForAnchor(
        block.getBoundingClientRect().top + window.scrollY,
        position.offset,
        markerLine(),
      )
    : scrollForProgress(readingGeometry(), position ? position.progress : 0);
  window.scrollTo({ top: Math.max(0, target), behavior: "auto" });
  await nextFrame();
  open.restoring = false;
  measure(true);
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
  jumpButton.addEventListener("click", openJump);
  jumpSearch.addEventListener("input", (event) => renderJumpResults(event.target.value));
  window.addEventListener("scroll", () => scheduleMeasure(), { passive: true });
  window.addEventListener("resize", () => scheduleMeasure(false));
  window.addEventListener("pagehide", savePosition);
  // A phone that backgrounds the tab and kills it later may never fire
  // `pagehide`, and "closes their browser" is the whole point of the mark.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") savePosition();
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
  };
  renderReader(manuscript, entry, section);
  if (showsChronos(preferences)) await loadScenes();
  // Only the spot you actually left carries an anchor, and only if it is in
  // this section: opening any other section starts it at the top.
  const spot = (readPosition(storage, readerUser, manuscript.book) || {}).last;
  const here = spot && spot.volume === entry.volume.id
    && spot.section === section.id ? spot : null;
  await restorePosition(here);
}

async function start() {
  if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
  wire();
  applyPreferences();
  const query = new URLSearchParams(window.location.search);
  const book = query.get("book");
  if (!book) {
    renderShelf((await api.books()).books);
    return;
  }

  const manuscript = await api.manuscript(book);
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
