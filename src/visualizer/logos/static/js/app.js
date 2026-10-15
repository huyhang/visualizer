// Logos' three-page reader: manuscript shelf, book contents, and one section.
// Navigation uses ordinary links and full page loads so bookmarks, new tabs,
// and the browser's back button work without a client-side router.

import { ApiError, BASE, api } from "./api.js";
import { boundaryGesture } from "./boundary.js";
import { compactAction } from "./compactaction.js";
import { createContentManager } from "./contentmanager.js";
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
import {
  filterAnnotations, filterIssues, reviewPage, sectionKindName,
} from "./review.js";
import { beginWriting, writerUrl } from "./writerlinks.js";

const root = document.documentElement;
const content = document.getElementById("content");
const toolbar = document.getElementById("reader-toolbar");
const modeButton = document.getElementById("mode-toggle");
const writeButton = document.getElementById("write-open");
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
const reviewButton = document.getElementById("review-open");
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
const volumeDialog = document.getElementById("volume-create-dialog");
const volumeForm = document.getElementById("volume-create-form");
const volumeName = document.getElementById("volume-create-name");
const volumeOverview = document.getElementById("volume-create-overview");
const volumeError = document.getElementById("volume-create-error");
const renameDialog = document.getElementById("volume-rename-dialog");
const renameForm = document.getElementById("volume-rename-form");
const renameName = document.getElementById("volume-rename-name");
const renameOverview = document.getElementById("volume-rename-overview");
const renameError = document.getElementById("volume-rename-error");
const sectionDialog = document.getElementById("section-create-dialog");
const sectionForm = document.getElementById("section-create-form");
const sectionTitle = document.getElementById("section-create-title");
const sectionVolume = document.getElementById("section-create-volume");
const sectionKind = document.getElementById("section-create-kind");
const sectionError = document.getElementById("section-create-error");
const moveDialog = document.getElementById("section-move-dialog");
const moveForm = document.getElementById("section-move-form");
const moveTitle = document.getElementById("section-move-title");
const moveVolume = document.getElementById("section-move-volume");
const movePosition = document.getElementById("section-move-position");
const moveError = document.getElementById("section-move-error");
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
let managingContents = false;
let reviewState = null;

// The glyph carries the state too, not just the word: the label is visually
// hidden on a phone, so a fixed mark would leave the compacted button saying
// nothing about which view you are in.
const MODE_TEXT = {
  focused: ["Focused", "▯", "Prose and bookmarks — nothing from any other service. Switch to Full view."],
  full: ["Full view", "◫", "With the Chronos scenes this section was written from. Switch to Focused."],
};

// A stable line near the top of the viewport is anchored to a manuscript block
// so a typeface or window-width change can still restore the same words.
const markerLine = () => Math.min(96, window.innerHeight / 3);
const home = () => `${BASE}/`;

function bookUrl(book) {
  return `${home()}?${new URLSearchParams({ book })}`;
}

function reviewUrl(book, tab = "notes") {
  return `${home()}?${new URLSearchParams({ book, review: tab })}`;
}

function readerUrl(book, volume, section, block = null, draft = null) {
  const query = { book, volume, section };
  if (block) query.block = block;
  if (draft) query.draft = draft;
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

// The page is headed "Book contents" above the series title, so an action that
// says "series" says it three times over. Dropping the word is what lets all
// seven keep their words in the reading measure -- with it they needed about
// 964px against 944, and a row of seven unexplained glyphs was the price.
function bookActions(manuscript) {
  const canWrite = manuscript.permissions.write;
  const hasVolumes = manuscript.volumes.length > 0;
  const actions = [];
  const button = (label, glyph, onclick, className = "btn ghost", extra = {}) =>
    compactAction({ label, glyph, className, onclick, ...extra });

  if (canWrite) {
    actions.push(button(
      "New volume", "▤", () => contentManager.openVolumeCreator(manuscript), "btn",
    ));
  }
  if (canWrite && hasVolumes) {
    actions.push(button(
      "New section", "+", () => contentManager.openSectionCreator(manuscript),
    ));
    actions.push(button(
      managingContents ? "Done arranging" : "Manage contents",
      managingContents ? "✓" : "↕",
      () => {
        managingContents = !managingContents;
        renderBook(manuscript);
      },
      managingContents ? "btn" : "btn ghost",
      { "aria-pressed": String(managingContents) },
    ));
  }
  if (hasVolumes) {
    actions.push(
      button("Search", "⌕", openSearch),
      button("Bookmarks", "◆", () => openBookmarks().catch(
        (error) => showTransientError(error.message),
      )),
    );
    if (canWrite) actions.push(button("Publish", "⇩", openPublication));
  }
  if (manuscript.rev) {
    actions.push(
      button("Review", "◎", () => { window.location.href = reviewUrl(manuscript.book); }),
    );
  }
  return el("div", { class: "book-actions compact-actions" }, actions);
}

function hideReaderChrome() {
  toolbar.hidden = true;
  progressRegion.hidden = true;
  open = null;
  reviewState = null;
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
  const actionable = row.has_manuscript || row.permissions.write;
  return el("article", { class: `card${actionable ? "" : " inert"}` }, [
    row.has_manuscript
      ? el("a", { class: "card-link", href: bookUrl(row.book) }, [heading])
      : heading,
    el("p", { class: "card-sub", text: row.book }),
    !row.has_manuscript && row.permissions.write ? el("button", {
      class: "btn sm", type: "button", text: "Start writing",
      onclick: () => api.manuscript(row.book)
        .then((manuscript) => beginWriting(manuscript, BASE))
        .catch((error) => showTransientError(error.message || "The manuscript could not be started.")),
    }) : null,
    el("p", { class: "card-meta", text: summary }),
    furthest ? continueLink(row.book, furthest) : null,
  ]);
}

function renderShelf(books) {
  hideReaderChrome();
  managingContents = false;
  contentManager.reset();
  pageManuscript = null;
  document.title = "Logos — manuscripts";
  prunePositions(
    storage,
    readerUser,
    books.filter((book) => book.has_manuscript).map((book) => book.book),
  );
  fill(content, [
    el("div", { class: "page-heading" }, [
      el("p", { class: "eyebrow", text: "Manuscript library" }),
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
    return entry ? {
      mark: {
        ...mark,
        volume: entry.volume.id,
        section: entry.section.id,
      },
      entry,
    } : null;
  };
  const last = locate(saved.last);
  const furthest = locate(saved.furthest);
  if (!last && !furthest) {
    forgetPosition(storage, readerUser, manuscript.book);
    return null;
  }
  const result = { last: last || furthest, furthest: furthest || last };
  if (
    result.last.mark.volume !== saved.last?.volume
    || result.furthest.mark.volume !== saved.furthest?.volume
  ) {
    storePosition(storage, readerUser, manuscript.book, {
      last: result.last.mark,
      furthest: result.furthest.mark,
    });
  }
  return result;
}

/**
 * The kind to print above a row's name, or null when it would say nothing.
 *
 * An untitled section is *named* for its kind already, and a row under a run
 * heading has just been told what kind it is -- unless the label carries a
 * number the heading does not.
 */
function sectionRow(manuscript, volume, section, marks, management = null) {
  const resume = marks && marks.furthest;
  const isResume = resume
    && resume.mark.volume === volume.id
    && resume.mark.section === section.id;
  // An untitled section is named for its kind already, so the label would only
  // say it twice. Nothing else in the outline names a kind: every row carries
  // its own, which is why a heading above a run of them has nothing to add.
  const kind = section.title ? sectionLabel(section) : null;
  const count = words(section.word_count);
  const controls = management ? el("span", { class: "section-manage-actions" }, [
    el("button", {
      class: "drag-handle", type: "button", text: "⠿", draggable: "true",
      title: `Drag ${sectionName(section)}`,
      "aria-label": `Drag to move ${sectionName(section)}`,
      ondragstart: (event) => contentManager.startDrag(event, {
        type: "section", id: section.id, volume, section,
      }),
      ondragend: contentManager.finishDrag,
      // Touch raises no drag events at all, so the same handle carries a
      // pointer gesture; it ignores the mouse, which has the native drag.
      onpointerdown: (event) => contentManager.beginTouchDrag(event, {
        type: "section", id: section.id, volume, section,
      }),
    }),
    el("button", {
      class: "order-button", type: "button", text: "↑",
      title: "Move up", "aria-label": `Move ${sectionName(section)} up`,
      disabled: management.index === 0,
      onclick: () => contentManager.placeSection(
        manuscript, volume, section, volume,
        volume.sections[management.index - 1]?.id || null,
      ),
    }),
    el("button", {
      class: "order-button", type: "button", text: "↓",
      title: "Move down", "aria-label": `Move ${sectionName(section)} down`,
      disabled: management.index === volume.sections.length - 1,
      onclick: () => contentManager.placeSection(
        manuscript, volume, section, volume,
        volume.sections[management.index + 2]?.id || null,
      ),
    }),
    manuscript.volumes.length > 1 ? el("button", {
      class: "move-button", type: "button", text: "Move…",
      onclick: () => contentManager.openSectionMover(manuscript, volume, section),
    }) : null,
  ]) : null;
  return el("li", {
    class: `section-row${isResume ? " resume" : ""}${management ? " managing" : ""}`,
    // The touch hit-test reads geometry off the page, since a captured pointer
    // never reports what is underneath it.
    "data-volume": volume.id,
    "data-section": section.id,
    ondragover: management ? (event) => contentManager.acceptDrop(event, "section") : null,
    ondragleave: management ? contentManager.leaveDrop : null,
    ondrop: management ? (event) => {
      const dragged = contentManager.takeDragged("section");
      if (!dragged) return;
      event.preventDefault();
      event.stopPropagation();
      contentManager.finishDrag(event);
      contentManager.placeSection(
        manuscript, dragged.volume, dragged.section, volume, section.id,
      );
    } : null,
  }, [
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
    manuscript.permissions.write && !management ? el("a", {
      class: "section-edit-link",
      href: writerUrl(BASE, manuscript.book, volume.id, section.id),
      text: "Edit",
      "aria-label": `Edit ${sectionName(section)}`,
    }) : null,
    controls,
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
  managing = false, volumeIndex = 0,
) {
  const summary = searching
    ? `${volume.sections.length} matching ${volume.sections.length === 1 ? "section" : "sections"}`
    : meta(
        `${volume.section_count} ${volume.section_count === 1 ? "section" : "sections"}`,
        words(volume.word_count),
      );
  // One argument on purpose: `Array.map` would otherwise hand the row builder
  // an index as its second.
  const row = (section, index) => sectionRow(
    manuscript, volume, section, marks, managing ? { index } : null,
  );
  const sectionList = searching || managing
    ? el("ol", { class: "section-list" }, volume.sections.map(row))
    : pagedSectionList(volume.sections, page, row, volume.title, rememberPage);
  return el("details", {
    class: `volume-card${managing ? " managing" : ""}`,
    "data-volume": volume.id,
    open: managing || expanded,
    ontoggle: (event) => rememberOpen(event.currentTarget.open),
  }, [
    el("summary", {
      class: "volume-summary",
      ondragover: managing ? (event) => contentManager.acceptDrop(event, "volume") : null,
      ondragleave: managing ? contentManager.leaveDrop : null,
      ondrop: managing ? (event) => {
        const dragged = contentManager.takeDragged("volume");
        if (!dragged) return;
        event.preventDefault();
        event.stopPropagation();
        contentManager.finishDrag(event);
        contentManager.reorderVolume(manuscript, dragged.id, volume.id);
      } : null,
    }, [
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
    managing ? el("div", { class: "volume-manage-actions" }, [
      el("button", {
        class: "drag-handle", type: "button", text: "⠿", draggable: "true",
        title: `Drag ${volume.title}`, "aria-label": `Drag to move ${volume.title}`,
        ondragstart: (event) => contentManager.startDrag(event, {
          type: "volume", id: volume.id,
        }),
        ondragend: contentManager.finishDrag,
        onpointerdown: (event) => contentManager.beginTouchDrag(event, {
          type: "volume", id: volume.id,
        }),
      }),
      el("button", {
        class: "order-button", type: "button", text: "↑", title: "Move volume up",
        "aria-label": `Move ${volume.title} up`, disabled: volumeIndex === 0,
        onclick: () => contentManager.reorderVolume(
          manuscript,
          volume.id,
          manuscript.volumes[volumeIndex - 1]?.id || null,
        ),
      }),
      el("button", {
        class: "order-button", type: "button", text: "↓", title: "Move volume down",
        "aria-label": `Move ${volume.title} down`,
        disabled: volumeIndex === manuscript.volumes.length - 1,
        onclick: () => contentManager.reorderVolume(
          manuscript,
          volume.id,
          manuscript.volumes[volumeIndex + 2]?.id || null,
        ),
      }),
      el("span", { class: "manage-hint", text: "Drag to reorder" }),
    ]) : null,
    volume.sections.length
      ? sectionList
      : el("p", { class: "volume-empty", text: "No sections yet." }),
    managing ? el("div", {
      class: "section-drop-end",
      ondragover: (event) => contentManager.acceptDrop(event, "section"),
      ondragleave: contentManager.leaveDrop,
      ondrop: (event) => {
        const dragged = contentManager.takeDragged("section");
        if (!dragged) return;
        event.preventDefault();
        contentManager.finishDrag(event);
        contentManager.placeSection(
          manuscript, dragged.volume, dragged.section, volume, null,
        );
      },
    }, [el("span", { text: "Drop at end" })]) : null,
    manuscript.permissions.write ? el("div", { class: "volume-actions" }, [
      managing ? el("button", {
        class: "new-chapter", type: "button", text: "Rename",
        "aria-label": `Rename volume ${volume.title}`,
        onclick: () => contentManager.openVolumeRenamer(manuscript, volume.id),
      }) : null,
      el("button", {
        class: "new-chapter", type: "button", text: "+ New section",
        onclick: () => contentManager.openSectionCreator(manuscript, volume.id),
      }),
    ]) : null,
  ]);
}

function outlineBrowser(manuscript, marks, managing = false) {
  const total = sectionCount(manuscript.volumes);
  const list = el("div", { class: "volume-list" });
  // The volume that opens is the one you were last in, not the one you got
  // furthest into: after going back to re-read, the page should show you
  // where you are and leave "Continue reading" to offer the way forward.
  const here = marks && marks.last;
  const opened = manuscript.volumes.some(
    (volume) => volume.id === contentManager.preferredVolume(),
  ) ? contentManager.preferredVolume() : defaultOpenVolume(manuscript, here && here.mark);
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
      ? filtered.map((volume, index) => volumeCard(
          manuscript,
          volume,
          marks,
          managing || searching || expanded.get(volume.id),
          searching,
          pages.get(volume.id) || 0,
          (page) => pages.set(volume.id, page),
          (isOpen) => {
            if (!searching) expanded.set(volume.id, isOpen);
          },
          managing,
          index,
        ))
      : [el("p", { class: "empty outline-empty", text: "No sections match your search." })]);
  };

  if (!total || managing) {
    render("");
    return el("div", { class: `outline-browser${managing ? " managing" : ""}` }, [
      managing ? el("p", {
        class: "manage-help muted",
      }, [
        el("span", {
          text: "Drag sections or volumes into place, or use the arrow and Move controls.",
        }),
        el("span", {
          id: "contents-save-status", class: "contents-save-status",
          role: "status", "aria-live": "polite",
        }),
      ]) : null,
      list,
    ]);
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

function pendingMoveNotices(manuscript) {
  return (manuscript.pending_section_moves || []).map((pending) => {
    const target = manuscript.volumes.find(
      (volume) => volume.id === pending.target_volume,
    );
    const label = pending.title || pending.section;
    const destination = target ? target.title : pending.target_volume;
    const status = el("span", {
      class: "move-warning-status",
      role: "status",
      "aria-live": "polite",
    });
    return el("section", { class: "reader-notice move-warning", role: "alert" }, [
      el("span", { class: "move-warning-copy" }, [
        el("strong", { text: "Move interrupted" }),
        el("span", {
          text: `${label} is safe but has not finished moving to ${destination}.`,
        }),
        status,
      ]),
      manuscript.permissions.write ? el("button", {
        class: "btn sm", type: "button", text: "Finish move",
        onclick: async (event) => {
          event.currentTarget.disabled = true;
          await contentManager.finishPendingMove(manuscript, pending, status);
          if (event.currentTarget.isConnected) event.currentTarget.disabled = false;
        },
      }) : el("span", {
        class: "muted", text: "An editor must finish this move.",
      }),
    ]);
  });
}

function renderBook(manuscript, notice = null) {
  hideReaderChrome();
  pageManuscript = manuscript;
  contentManager.setManuscript(manuscript);
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
      bookActions(manuscript),
    ]),
    notice ? el("p", { class: "reader-notice", role: "status", text: notice }) : null,
    pendingMoveNotices(manuscript),
    resumeCallout(manuscript, marks),
    manuscript.volumes.length
      ? outlineBrowser(manuscript, marks, managingContents)
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
  writeButton.hidden = !manuscript.permissions.write;
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
      open.drafts && open.drafts.length > 1 ? readerDraftPicker() : null,
      open.draftMissing ? el("p", {
        class: "reader-draft-notice", role: "status",
        text: "That draft is no longer available. Showing the primary draft.",
      }) : null,
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

function readerDraftPicker() {
  const selected = open.draft;
  return el("label", { class: "reader-draft-picker" }, [
    el("span", { text: selected.primary ? "Reading draft" : "Previewing alternate draft" }),
    el("select", {
      "aria-label": "Reader draft",
      onchange: (event) => {
        const chosen = open.drafts.find((draft) => draft.id === event.target.value);
        window.location.href = readerUrl(
          open.manuscript.book,
          open.volume.id,
          open.section.id,
          null,
          chosen && !chosen.primary ? chosen.id : null,
        );
      },
    }, open.drafts.map((draft) => el("option", {
      value: draft.id,
      text: `${draft.name}${draft.primary ? " (Primary)" : ""}`,
      selected: draft.id === selected.id,
    }))),
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

// `pending` is the same request already on its way, asked for with the section.
async function loadScenes(pending = null) {
  if (!open || open.scenesLoaded || !scenePanelNode) return;
  open.scenesLoaded = true;
  try {
    fillScenes(await (pending
      || api.scenes(open.manuscript.book, open.volume.id, open.section.id)));
  } catch (error) {
    open.scenesLoaded = false;
    sceneLoadFailed(error);
  }
}

// -- private notes, checklists and bookmarks --------------------------------

// `pending` is the same request already on its way, asked for with the section.
async function loadReaderData(pending = null) {
  if (!pageManuscript || readerItemsLoaded) return;
  const payload = await (pending || api.readerItems(pageManuscript.book));
  readerItems = payload.items;
  readerItemsLoaded = true;
  refreshReaderData();
}

function currentReaderData() {
  if (!open) return { notes: [], bookmarks: [], sectionChecklist: [], bookChecklist: [] };
  return dataForSection(
    readerItems, open.volume.id, open.section.id, open.draft && open.draft.id,
  );
}

function refreshReaderData() {
  if (open) {
    decorateParagraphs();
    renderPersonalPanel();
    if (bookmarksDialog.open) renderBookmarks();
  }
  if (reviewState && reviewState.tab === "notes") renderReviewAnnotations();
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
    const bookmark = bookmarkAt(
      data.bookmarks,
      open.volume.id,
      open.section.id,
      blockId,
      open.draft && open.draft.id,
    );
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
        ...(!open.draft.primary ? { draft: open.draft.id } : {}),
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
  if (!context) return;
  const text = itemEditorText.value.trim();
  const editing = context.item || null;
  if (!editing && !open) return;
  let saved;
  if (editing) {
    saved = await api.updateReaderItem(
      pageManuscript.book, editing.id, { text }, editing.rev,
    );
  } else if (context.kind === "note") {
    saved = await api.createReaderItem(pageManuscript.book, {
      kind: "note", volume: open.volume.id, section: open.section.id,
      block: context.block, text,
      ...(!open.draft.primary ? { draft: open.draft.id } : {}),
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

function clearToasts() {
  document.querySelectorAll(".reader-toast").forEach((node) => node.remove());
}

function showTransientError(message) {
  clearToasts();
  const notice = el("p", { class: "reader-toast", role: "alert", text: message });
  document.body.appendChild(notice);
  window.setTimeout(() => notice.remove(), 3500);
}

/**
 * A failure the writer can act on. It stays until retried or dismissed: a
 * three-second toast is no place to put the only way out of a half-finished
 * move.
 */
function showRetryError(message, retry) {
  clearToasts();
  const notice = el("p", { class: "reader-toast actionable", role: "alert" }, [
    el("span", { text: message }),
    el("span", { class: "toast-actions" }, [
      el("button", {
        class: "btn sm", type: "button", text: "Retry",
        onclick: () => { notice.remove(); retry(); },
      }),
      el("button", {
        class: "icon-btn", type: "button", text: "×",
        "aria-label": "Dismiss", onclick: () => notice.remove(),
      }),
    ]),
  ]);
  document.body.appendChild(notice);
}

const contentManager = createContentManager({
  api,
  base: BASE,
  editorUrl: writerUrl,
  navigate: (url) => { window.location.href = url; },
  render: renderBook,
  showError: showTransientError,
  showRetry: showRetryError,
  elements: {
    content,
    volumeDialog,
    volumeForm,
    volumeName,
    volumeOverview,
    volumeError,
    renameDialog,
    renameForm,
    renameName,
    renameOverview,
    renameError,
    sectionDialog,
    sectionForm,
    sectionTitle,
    sectionVolume,
    sectionKind,
    sectionError,
    moveDialog,
    moveForm,
    moveTitle,
    moveVolume,
    movePosition,
    moveError,
    closeButtons: document.querySelectorAll("[data-dialog-close]"),
  },
});

// -- series review -----------------------------------------------------------

function reviewTab(manuscript, tab, label) {
  return el("a", {
    class: `review-tab${reviewState.tab === tab ? " active" : ""}`,
    href: reviewUrl(manuscript.book, tab),
    text: label,
    ...(reviewState.tab === tab ? { "aria-current": "page" } : {}),
  });
}

function reviewSelect(label, options, value, onChange) {
  return el("label", { class: "review-filter" }, [
    el("span", { text: label }),
    el("select", { onchange: onChange }, options.map(([key, text]) => el("option", {
      value: key, text, selected: key === value,
    }))),
  ]);
}

function reviewLocationSelect(includeSeries, render) {
  const options = [["all", "All locations"]];
  if (includeSeries) options.push(["series", "Series"]);
  for (const volume of pageManuscript.volumes) {
    options.push([`volume:${volume.id}`, `Volume ${volume.number} · ${volume.title}`]);
    for (const section of volume.sections) {
      options.push([
        `section:${volume.id}:${section.id}`,
        `\u00a0\u00a0${sectionName(section)}`,
      ]);
    }
  }
  return reviewSelect("Location", options, reviewState.filters.location, (event) => {
    reviewState.filters.location = event.target.value;
    render();
  });
}

/** The volume a location filter narrows to, if it narrows to one. */
function locationVolume(location) {
  const [kind, volume] = (location || "").split(":");
  return kind === "volume" || kind === "section" ? volume : null;
}

function annotationContext(item) {
  const entry = item.scope === "book" ? null : findSection(
    pageManuscript, item.volume, item.section,
  );
  return {
    ...item,
    volume_title: entry ? entry.volume.title : "Series",
    section_title: entry ? sectionName(entry.section) : "Series checklist",
    entry,
  };
}

function annotationHref(item) {
  if (item.available === false) return null;
  if (item.scope === "book") return bookUrl(pageManuscript.book);
  if (!item.entry) return null;
  return readerUrl(
    pageManuscript.book,
    item.volume,
    item.section,
    item.kind === "note" ? item.block : null,
    item.kind === "note" ? item.draft : null,
  );
}

function annotationCard(item) {
  const location = item.scope === "book"
    ? "Series"
    : `${item.volume_title} · ${item.section_title}`;
  const draft = item.kind === "note" && !item.draft_primary
    ? ` · ${item.draft_name || "Alternate draft"}` : "";
  const destination = annotationHref(item);
  return el("article", {
    class: `review-card review-${item.kind}${item.available === false ? " unavailable" : ""}`,
  }, [
    el("div", { class: "review-card-main" }, [
      item.kind === "checklist" ? el("input", {
        type: "checkbox",
        ...(item.done ? { checked: true } : {}),
        "aria-label": `${item.done ? "Reopen" : "Complete"} ${item.text}`,
        onchange: (event) => updateChecklist(item, { done: event.target.checked }),
      }) : el("span", { class: "review-note-mark", "aria-hidden": "true", text: "✎" }),
      el("div", {}, [
        el("strong", { class: item.done ? "done" : "", text: item.text }),
        item.excerpt ? el("q", { text: item.excerpt }) : null,
        el("small", {
          text: item.available === false
            ? `${location}${draft} · Location unavailable` : `${location}${draft}`,
        }),
      ]),
    ]),
    el("div", { class: "review-card-actions" }, [
      destination ? el("a", { class: "btn ghost sm", href: destination, text: "Open" }) : null,
      el("button", {
        class: "btn ghost sm", type: "button", text: "Edit",
        onclick: () => openItemEditor({
          kind: item.kind,
          scope: item.scope,
          block: item.block,
          item,
        }),
      }),
    ]),
  ]);
}

function annotationOrder(item) {
  if (item.scope === "book") return -1;
  return reviewState.sectionOrder.get(`${item.volume}/${item.section}`)
    ?? Number.MAX_SAFE_INTEGER;
}

function showMoreButton(next, render) {
  return el("button", {
    class: "btn ghost review-more", type: "button",
    text: `Show ${next.toLocaleString()} more`,
    onclick: () => { reviewState.shown += COACHING_PAGE; render(); },
  });
}

function renderReviewAnnotations() {
  if (!reviewState || reviewState.tab !== "notes" || !readerItemsLoaded) return;
  const all = readerItems.map(annotationContext);
  const matched = filterAnnotations(all, reviewState.filters)
    .sort((left, right) => annotationOrder(left) - annotationOrder(right));
  const page = reviewPage(matched, reviewState.shown, COACHING_PAGE);
  reviewState.status.textContent = `${page.visible.length.toLocaleString()} of `
    + `${matched.length.toLocaleString()} items`;
  const groups = new Map();
  for (const item of page.visible) {
    const key = item.scope === "book"
      ? "Series"
      : `${item.volume_title} · ${item.section_title}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  fill(reviewState.results, groups.size
    ? [
        ...[...groups].map(([label, items]) => el("section", { class: "review-group" }, [
          el("h2", { text: label }),
          el("div", { class: "review-card-list" }, items.map(annotationCard)),
        ])),
        page.remaining ? showMoreButton(page.next, renderReviewAnnotations) : null,
      ]
    : [el("p", { class: "empty", text: "No notes or checklists match these filters." })]);
}

// The writing page's own keys, so the Review page and its Coach share one
// dialect and one set of ignored rules. See `frontend/src/logos/logic/preferences.ts`.
const writingDialectKey = () => `logos-writing-dialect:${encodeURIComponent(readerUser)}`;
const writingIgnoredKey = () => `logos-writing-ignored:${encodeURIComponent(readerUser)}`;

function ignoredWritingRules() {
  try {
    return JSON.parse(localStorage.getItem(writingIgnoredKey()) || "[]");
  } catch (_error) {
    return [];
  }
}

function writingDialect() {
  try {
    return localStorage.getItem(writingDialectKey()) || "en-US";
  } catch (_error) {
    return "en-US";
  }
}

function rememberWritingDialect(dialect) {
  try {
    localStorage.setItem(writingDialectKey(), dialect);
  } catch (_error) { /* the choice still applies to this page */ }
}

function issueHref(issue) {
  const target = new URL(writerUrl(
    BASE, pageManuscript.book, issue.volume, issue.section, issue.draft,
  ), window.location.origin);
  // `block` lands the caret on the passage; `coach` opens the panel beside it.
  // A flag, not the finding's id -- the panel reviews the draft afresh on open
  // and has no way to be pointed at one row of a list it has yet to build.
  target.searchParams.set("block", issue.block);
  target.searchParams.set("coach", "1");
  return target.href;
}

function coachingCard(issue) {
  return el("article", { class: "review-card coaching-card" }, [
    el("div", { class: "review-card-main" }, [
      el("span", { class: "review-category", text: issue.category }),
      el("div", {}, [
        el("strong", { text: issue.title }),
        el("p", { text: issue.message }),
        el("q", { text: issue.excerpt }),
        el("small", {
          text: `${issue.volume_title} · ${sectionKindName(issue)}`
            + `${issue.primary ? "" : ` · ${issue.draft_name}`}`,
        }),
      ]),
    ]),
    el("div", { class: "review-card-actions" }, [
      el("a", { class: "btn sm", href: issueHref(issue), text: "Open in editor" }),
    ]),
  ]);
}

// A card is about ten elements, so a whole epic series at once would be a
// six-figure node count built in one synchronous pass -- the tab stops
// responding long before the writer has read the first screen. A page at a
// time, extended on request, costs the same to read and nothing to render.
const COACHING_PAGE = 200;

function coachingSummary(shown, total) {
  const suffix = reviewState.coaching.truncated
    ? ` · first ${total.toLocaleString()} of ${
      reviewState.coaching.issue_count.toLocaleString()}`
    : "";
  const scope = reviewState.volume
    ? "this volume" : `${reviewState.coaching.reviewed_drafts} drafts`;
  return `${shown.toLocaleString()} of ${total.toLocaleString()} `
    + `${total === 1 ? "suggestion" : "suggestions"} across ${scope}${suffix}`;
}

function renderReviewCoaching() {
  if (!reviewState || reviewState.tab !== "coaching" || !reviewState.coaching) return;
  const all = reviewState.coaching.issues || [];
  const matched = filterIssues(all, {
    ...reviewState.filters,
    ignored: ignoredWritingRules(),
  });
  const page = reviewPage(matched, reviewState.shown, COACHING_PAGE);
  reviewState.status.textContent = coachingSummary(
    page.visible.length, matched.length,
  );
  fill(reviewState.results, matched.length
    ? [
        ...page.visible.map(coachingCard),
        page.remaining ? showMoreButton(page.next, renderReviewCoaching) : null,
      ]
    : [el("p", { class: "empty", text: "No coaching suggestions match these filters." })]);
}

async function loadReviewCoaching() {
  const requestToken = Symbol("series-review");
  reviewState.requestToken = requestToken;
  reviewState.shown = COACHING_PAGE;
  reviewState.volume = locationVolume(reviewState.filters.location);
  reviewState.status.textContent = reviewState.volume
    ? "Reviewing this volume…" : "Reviewing the series…";
  fill(reviewState.results, [el("p", { class: "empty", text: "Checking each draft…" })]);
  try {
    const result = await api.seriesWritingReview(
      pageManuscript.book, reviewState.dialect, reviewState.includeAlternates,
      reviewState.volume,
    );
    if (!reviewState || reviewState.requestToken !== requestToken) return;
    reviewState.coaching = result;
    renderReviewCoaching();
  } catch (error) {
    if (!reviewState || reviewState.requestToken !== requestToken) return;
    reviewState.status.textContent = "Review unavailable";
    fill(reviewState.results, [el("p", {
      class: "form-error", text: error.message || "The series could not be reviewed.",
    })]);
  }
}

function reviewControls(tab) {
  // Narrowing the filters starts the page again: "show more" is a position in
  // one list, and keeping it across a change of list shows an arbitrary slice.
  const rerender = tab === "notes" ? renderReviewAnnotations : renderReviewCoaching;
  const refilter = () => { reviewState.shown = COACHING_PAGE; rerender(); };
  const query = el("input", {
    class: "review-search", type: "search", placeholder: "Filter this review",
    "aria-label": "Filter review results",
    oninput: (event) => {
      reviewState.filters.query = event.target.value;
      refilter();
    },
  });
  if (tab === "notes") {
    return el("div", { class: "review-controls" }, [
      query,
      reviewLocationSelect(true, refilter),
      reviewSelect("Type", [["all", "All items"], ["note", "Notes"],
        ["checklist", "Checklists"]], "all", (event) => {
        reviewState.filters.kind = event.target.value;
        refilter();
      }),
      reviewSelect("Status", [["all", "Any status"], ["open", "Open"],
        ["completed", "Completed"]], "all", (event) => {
        reviewState.filters.status = event.target.value;
        refilter();
      }),
    ]);
  }
  return el("div", { class: "review-controls" }, [
    query,
    // Choosing a volume is not a filter over what was fetched -- it is a
    // smaller request. On a ten-volume series that is a tenth of the prose
    // read, a tenth of the payload, and the one control that makes reviewing
    // an epic practical at all.
    reviewLocationSelect(false, () => {
      if (locationVolume(reviewState.filters.location) !== reviewState.volume) {
        loadReviewCoaching();
      } else {
        refilter();
      }
    }),
    reviewSelect("Category", [["all", "All suggestions"], ["spelling", "Spelling"],
      ["grammar", "Grammar"], ["punctuation", "Punctuation"], ["spacing", "Spacing"],
      ["flow", "Flow"], ["style", "Style"]], "all", (event) => {
      reviewState.filters.category = event.target.value;
      refilter();
    }),
    reviewSelect("English", [["en-US", "US"], ["en-GB", "UK"]],
      reviewState.dialect, (event) => {
        reviewState.dialect = event.target.value;
        rememberWritingDialect(reviewState.dialect);
        loadReviewCoaching();
      }),
    el("label", { class: "review-alternates" }, [
      el("input", {
        type: "checkbox",
        onchange: (event) => {
          reviewState.includeAlternates = event.target.checked;
          loadReviewCoaching();
        },
      }),
      el("span", { text: "Include alternate drafts" }),
    ]),
  ]);
}

async function renderReview(manuscript, requestedTab) {
  hideReaderChrome();
  pageManuscript = manuscript;
  const tab = requestedTab === "coaching" && manuscript.permissions.write
    ? "coaching" : "notes";
  const status = el("p", { class: "review-status muted", "aria-live": "polite" });
  const results = el("div", { class: "review-results" });
  reviewState = {
    tab,
    status,
    results,
    filters: {
      query: "", kind: "all", status: "all", category: "all", location: "all",
    },
    dialect: writingDialect(),
    includeAlternates: false,
    coaching: null,
    volume: null,
    shown: COACHING_PAGE,
    sectionOrder: new Map(pageManuscript.volumes.flatMap((volume) =>
      volume.sections.map((section) => `${volume.id}/${section.id}`))
      .map((key, index) => [key, index])),
  };
  document.title = `Review — ${manuscript.title || manuscript.book}`;
  fill(content, [
    el("div", { class: "review-page" }, [
      el("a", { class: "back-link", href: bookUrl(manuscript.book), text: "← Series contents" }),
      el("header", { class: "review-heading" }, [
        el("p", { class: "eyebrow", text: manuscript.title || manuscript.book }),
        el("h1", { text: "Review series" }),
        el("p", { class: "lead", text: "Everything that needs another look, in one place." }),
      ]),
      el("nav", { class: "review-tabs", "aria-label": "Review sections" }, [
        reviewTab(manuscript, "notes", "Notes & checklists"),
        manuscript.permissions.write
          ? reviewTab(manuscript, "coaching", "Coaching") : null,
      ]),
      reviewControls(tab),
      status,
      results,
    ]),
  ]);
  if (tab === "notes") {
    readerItems = [];
    readerItemsLoaded = false;
    await loadReaderData();
  } else {
    await loadReviewCoaching();
  }
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
            href: readerUrl(
              pageManuscript.book, item.volume, item.section, item.block, item.draft,
            ),
          }, [
            el("strong", { text: label }),
            el("span", {
              text: `${entry.volume.title} · ${sectionName(entry.section)}`
                + `${item.draft_primary ? "" : ` · ${item.draft_name || "Alternate draft"}`}`,
            }),
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
  const [label, glyph, hint] = MODE_TEXT[preferences.mode];
  modeButton.querySelector(".compact-action-label").textContent = label;
  modeButton.querySelector(".compact-action-glyph").textContent = glyph;
  modeButton.title = hint;
  modeButton.setAttribute("aria-pressed", String(preferences.mode === FULL));
}

function update(patch) {
  preferences = writePreferences(storage, patch);
  applyPreferences();
  scheduleMeasure(false);
}

function wire() {
  contentManager.wire();
  writeButton.addEventListener("click", () => {
    if (!open) return;
    const url = new URL(writerUrl(
      BASE, open.manuscript.book, open.volume.id, open.section.id,
      open.draft && open.draft.id,
    ), window.location.origin);
    const anchor = blockSnapshot().block;
    if (anchor) url.searchParams.set("block", anchor);
    window.location.href = url.href;
  });
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
  reviewButton.addEventListener("click", () => {
    if (pageManuscript) window.location.href = reviewUrl(pageManuscript.book);
  });
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

// A request whose failure is reported where it is awaited, later: marked handled
// now so the browser does not call it unhandled in the meantime.
function asked(request) {
  if (request) request.catch(() => {});
  return request;
}

async function openSection(manuscript, entry) {
  const { book } = manuscript;
  const volumeId = entry.volume.id;
  const sectionId = entry.section.id;
  // Everything the section needs that waits on nothing else, asked for at
  // once: one round trip to the server instead of one after another.
  const sectionCall = asked(api.section(book, volumeId, sectionId));
  const draftsCall = asked(
    manuscript.permissions.write ? api.drafts(book, volumeId, sectionId) : null,
  );
  const itemsCall = asked(api.readerItems(book));
  const scenesCall = asked(
    showsChronos(preferences) ? api.scenes(book, volumeId, sectionId) : null,
  );
  let section = await sectionCall;
  // `?mode=write` never reaches here: the server answers it with the writing
  // page's own shell (`writer_page.py`).
  const query = new URLSearchParams(window.location.search);
  let draft = {
    id: section.primary_draft_id,
    name: "Primary draft",
    primary: true,
  };
  let availableDrafts = [draft];
  let draftMissing = false;
  if (manuscript.permissions.write) {
    const listing = await draftsCall;
    availableDrafts = listing.drafts;
    const requested = query.get("draft");
    const found = availableDrafts.find((row) => row.id === requested);
    // A link to a draft that has since been deleted falls back to the primary,
    // but says so: silently showing different prose than the link promised is
    // how a writer edits the wrong draft.
    draftMissing = Boolean(requested && !found);
    draft = found || availableDrafts.find((row) => row.primary) || draft;
    if (!draft.primary) {
      const alternate = await api.draft(
        manuscript.book, entry.volume.id, entry.section.id, draft.id,
      );
      section = { ...section, document: alternate.document, word_count: alternate.word_count };
    }
  }
  open = {
    manuscript,
    volume: entry.volume,
    section,
    article: null,
    prose: null,
    scenesLoaded: false,
    restoring: true,
    navigating: false,
    draft,
    drafts: availableDrafts,
    draftMissing,
  };
  readerItems = [];
  readerItemsLoaded = false;
  renderReader(manuscript, entry, section);
  if (showsChronos(preferences)) await loadScenes(scenesCall);
  try {
    await loadReaderData(itemsCall);
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
  const query = new URLSearchParams(window.location.search);
  const book = query.get("book");
  // The settings and the manuscript are asked for together: neither waits on the other.
  const settingsCall = api.readerSettings()
    .catch(() => ({ sync_reading_position: false }));
  const manuscriptCall = asked(book ? api.manuscript(book) : null);
  readerSettings = await settingsCall;
  syncControl.checked = readerSettings.sync_reading_position;
  if (!book) {
    const books = (await api.books()).books;
    if (readerSettings.sync_reading_position) {
      await Promise.all(books.filter((row) => row.has_manuscript)
        .map((row) => syncStoredPosition(row.book)));
    }
    renderShelf(books);
    return;
  }

  // The stored position syncs (when the reader asked for that) while the manuscript arrives.
  const [manuscript] = await Promise.all([manuscriptCall, syncStoredPosition(book)]);
  if (query.get("review")) {
    await renderReview(manuscript, query.get("review"));
    return;
  }
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
  if (entry.volume.id !== volume) {
    const moved = readerUrl(
      manuscript.book,
      entry.volume.id,
      entry.section.id,
      query.get("block"),
      query.get("draft"),
    );
    window.history.replaceState(null, "", moved);
  }
  await openSection(manuscript, entry);
}

start().catch(showFailure);
