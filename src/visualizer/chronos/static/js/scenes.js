// The scene library for one book: every scene it holds, in story order, with
// the writing, editing and — the part that had no home before — the removing.
//
// Until now a scene could only be written from *inside* a plotline, which made
// two things awkward. A scene the writer abandoned mid-edit stayed in the book
// with no way to remove it, and a scene belonging to no thread yet was findable
// only through the Add-scene picker of a thread it was not part of. This view
// is the book's own list, so a scene is a thing you can keep house on.
//
// It is a route rather than a modal, unlike the plotline and scene editors:
// those are detours from reading one thread, while this is somewhere you go and
// stay a while — filtering, paging, working down a list.
//
// Three notes on the deletions, which are the only irreversible thing here:
//
// * **The table has no revisions.** Rows come from the browse endpoint, which
//   returns summaries; a write needs the scene itself. So every edit and delete
//   reads the scene first, which buys optimistic concurrency for the price of
//   one cheap request — a scene changed since the page was drawn refuses the
//   delete rather than silently overwriting someone.
// * **The server decides, the browser explains.** A scene in use, or one that
//   is the book's ending, is refused with a code and evidence; each gets a
//   dialog that says what is in the way and what to do about it, rather than a
//   toast with a sentence of server prose in it.
// * **One case is refused outright** — see `refuseWouldEmpty`.

import { api } from "./api.js";
import { calendarSwitcher, currentFor } from "./calendarview.js";
import { clear, el, toast } from "./dom.js";
import { entityTitle } from "./entities.js";
import { pager } from "./paging.js";
import { clearPeek, showScene } from "./peek.js";
import { confirmModal, modal } from "./picker.js";
import { loadScope, sceneForm } from "./sceneform.js";

const PER_PAGE = 20;

// The last filter+page per book, so coming back from a scene lands where you
// left — the same courtesy the plotline table extends.
const lastState = {};

export async function mountScenes(container, book, { onBooks, onBook }) {
  clear(container);
  const state = lastState[book] || { query: "", page: 1 };
  lastState[book] = state;

  let bookMeta = { title: book, permissions: {} };
  try { bookMeta = await api.getBook(book); } catch (e) { /* fall back to the id */ }
  const canWrite = Boolean((bookMeta.permissions || {}).write);
  const canDelete = Boolean((bookMeta.permissions || {}).delete);
  // Which Akasha world the scene form's pickers search. Asked once for the
  // whole visit rather than per form.
  const scope = await loadScope(book, bookMeta);
  // Scenes list the threads they belong to by id; the writer knows them by
  // name. Read once at mount — the membership itself is re-read on every
  // render, so only the naming is cached, and an unknown id shows as itself.
  const threadNames = await loadThreadNames(book);
  // Which scene the peek slot is currently showing, so an edit or a delete can
  // dismiss a card that has stopped being true (see `dropStalePeek`).
  let peeked = null;
  // Which of the book's calendars the When column is written in. Validated
  // against what the book actually has, so a reckoning detached since the
  // writer last visited quietly reverts to the primary instead of 404ing.
  let calendar = currentFor(book, bookMeta.calendars);

  const filterBox = el("input", {
    type: "search", class: "filter-box", placeholder: "Filter scenes…",
    autocomplete: "off", value: state.query,
  });
  const results = el("div", { class: "scene-results" },
    el("p", { class: "muted", text: "Loading…" }));

  container.appendChild(el("div", { class: "view table-view" }, [
    breadcrumb(bookMeta.title || book, onBooks, onBook),
    el("div", { class: "book-head" }, [
      el("h1", { class: "view-title", text: "Scenes" }),
      el("span", { class: "muted", text: bookMeta.title || book }),
      // Only when the book keeps more than one reckoning. Switching re-reads
      // the table: the labels come from the server's codec, never from here.
      calendarSwitcher(book, bookMeta.calendars, (chosen) => {
        calendar = chosen;
        render();
      }),
    ].filter(Boolean)),
    el("p", { class: "view-lead muted", text:
      "Every scene in this book, earliest first. Undated ones come last — they "
      + "are waiting for a place on the timeline, not missing one." }),
    el("div", { class: "filter-bar" }, [
      filterBox,
      canWrite ? el("button", {
        class: "btn sm", type: "button", text: "+ New scene", onclick: writeScene,
      }) : null,
    ].filter(Boolean)),
    results,
  ]));

  // -- the table -------------------------------------------------------------

  async function render() {
    try {
      const data = await api.listEvents(book, {
        filter: state.query, page: state.page, perPage: PER_PAGE, calendar,
      });
      state.page = data.page; // the server clamps an out-of-range page
      clear(results);
      results.appendChild(table(data.events));
      results.appendChild(pager(data, (p) => { state.page = p; render(); }, { noun: "scene" }));
    } catch (e) {
      clear(results);
      results.appendChild(el("p", { class: "empty", text: "Could not load the scenes." }));
      toast(e.message || "Could not load the scenes.", true);
    }
  }

  function table(rows) {
    if (!rows.length) return el("p", { class: "empty", text: emptyMessage() });
    return el("div", { class: "table-wrap" }, el("table", { class: "pl-table scene-table" }, [
      el("thead", {}, el("tr", {}, [
        el("th", { text: "When" }),
        el("th", { text: "Scene" }),
        el("th", { text: "Place" }),
        el("th", { text: "Used by" }),
        // Always present: the column carries Expand, which is a reading act.
        el("th", { class: "tools" }),
      ])),
      el("tbody", {}, rows.map(row)),
    ]));
  }

  function emptyMessage() {
    if (state.query) return "No scene matches your filter.";
    return canWrite
      ? "This book has no scenes yet — write the first one."
      : "This book has no scenes yet.";
  }

  function row(scene) {
    return el("tr", {}, [
      el("td", { class: "when" }, el("span", { class: "scene-when", text: scene.when })),
      el("td", {}, [
        el("span", { class: "pl-name", text: scene.title }),
        // The two facts a scene's row should carry beyond its name: whether it
        // is the book's ending, and whether it has been placed in time yet.
        scene.id === bookMeta.terminus
          ? el("span", { class: "badge terminus", text: "terminus" }) : null,
        scene.scheduled ? null : el("span", { class: "chip unscheduled", text: "unscheduled" }),
      ]),
      el("td", {}, place(scene)),
      el("td", {}, usedBy(scene.plotlines)),
      el("td", { class: "tools" }, el("div", { class: "scene-tools" }, [
        // Reading, not editing, so it is offered to everyone who can open the
        // book at all — unlike the two beside it.
        tool("⤢", "Expand — the whole scene, with its cast and places", () => expandScene(scene)),
        canWrite ? tool("✎", "Edit this scene", () => editScene(scene)) : null,
        // An editor who is not the owner sees this disabled rather than absent:
        // a missing control reads as "this cannot be done", where the truth is
        // "not by you". A reader, who cannot edit either, is shown neither.
        canWrite ? (canDelete
          ? tool("✕", "Delete this scene", () => deleteScene(scene))
          : el("button", {
              class: "icon-btn sm", type: "button", text: "✕", disabled: "",
              title: "Only the book's owner may delete a scene",
            })) : null,
      ])),
    ]);
  }

  // Where the scene happens, by the name the writer gave the article rather than
  // by its slug. Chronos stores only the reference, so the title is asked for
  // lazily and swapped in — the id shows meanwhile, and stays if the article has
  // been deleted or is not readable. Same pattern (and same memoised cache) as
  // the event cards; twenty rows sharing one location cost one request.
  function place(scene) {
    const node = el("span", { class: "muted", text: scene.location });
    if (scene.location_ref) {
      entityTitle(book, scene.location_ref).then((title) => { node.textContent = title; });
    }
    return node;
  }

  // A scene in no thread is not an error, but it is worth seeing: it is either
  // still to be threaded, or the leftover of an edit that was abandoned.
  function usedBy(plotlines) {
    if (!plotlines || !plotlines.length) {
      return el("span", { class: "muted unused", text: "not in any plotline" });
    }
    return el("div", { class: "chip-row" },
      plotlines.map((p) => el("span", { class: "chip", text: threadNames.get(p) || p })));
  }

  // -- reading one scene in full ---------------------------------------------

  // The whole scene beside the table: its timeframe, whatever role it plays in
  // the weave, its description, and its place, cast and items as chips that open
  // the article behind them. None of that is rendered here — `peek.js` owns the
  // slot and `cards.js` builds the card, which is the same pair the plotline
  // view's expanded card and the story graph already go through. So a reference
  // clicked here opens exactly the article card it opens there, and there is one
  // scene-rendering path in the app rather than three.
  //
  // Only the id and title are handed over. The row knows the scene's timing too,
  // but in the shape the *table* uses; the card fills that in from the scene
  // itself rather than being told it twice in two vocabularies.
  function expandScene(scene) {
    peeked = scene.id;
    showScene(book, { id: scene.id, title: scene.title });
  }

  // A card left open over a scene that has since been rewritten or deleted is
  // worse than no card: it is a confident, wrong answer. Cleared only when it is
  // *that* scene, so editing one scene does not dismiss the card you were
  // reading about another.
  function dropStalePeek(eventId) {
    if (peeked === eventId) {
      peeked = null;
      clearPeek();
    }
  }

  // -- writing and editing ---------------------------------------------------

  function writeScene() {
    openForm("Write a new scene", null, "Created");
  }

  async function editScene(scene) {
    const event = await loadScene(scene.id);
    if (event) openForm(`Edit “${event.title || event.id}”`, event, "Saved");
  }

  function openForm(title, event, verb) {
    const holder = el("div");
    const dialog = modal(title, holder);
    holder.appendChild(sceneForm(book, {
      // Start in whichever reckoning the page is being read in — the form then
      // offers the rest, so a scene can be dated in the calendar its *setting*
      // keeps rather than the one the table happens to be showing.
      scope, calendars: bookMeta.calendars || [], calendarId: calendar, event,
      onCancel: () => dialog.close(),
      onSaved: (saved) => {
        dialog.close();
        toast(`${verb} “${saved.title}”.`);
        dropStalePeek(saved.id);
        render();
      },
    }));
  }

  // The browse row carries no revision, so the scene itself is read before any
  // write. One request, and the edit is concurrency-safe rather than hopeful.
  async function loadScene(id) {
    try {
      return await api.getEvent(book, id);
    } catch (e) {
      toast(e.isNotFound ? "That scene no longer exists." : "Could not open that scene.", true);
      render(); // the list is out of date either way
      return null;
    }
  }

  // -- deleting --------------------------------------------------------------

  async function deleteScene(scene) {
    const event = await loadScene(scene.id);
    if (!event) return;
    // The book already told us its ending, so say so now rather than after a
    // "this cannot be undone" the server was always going to refuse. The 409
    // below is still the authority -- this only saves an alarming dead end.
    if (event.id === bookMeta.terminus) return explainTerminus(event);
    confirmModal(
      `Delete “${event.title || event.id}”?`,
      "The scene is removed from the book for good — there is no undo. The "
      + "characters, items and places it references are articles, and are not touched.",
      { yes: "Delete", danger: true, onYes: () => remove(event, false) },
    );
  }

  async function remove(event, detach) {
    try {
      await api.deleteEvent(book, event.id, event.rev, { detach });
      toast(`Deleted “${event.title || event.id}”.`);
      dropStalePeek(event.id);
      render();
    } catch (e) {
      if (e.code === "EVENT_IN_USE") return offerDetach(event, e.evidence.plotlines || []);
      if (e.code === "TERMINUS_IN_USE") return explainTerminus(event);
      // Covers both preconditions: the scene's own revision, and — when
      // detaching — each thread the server has to rewrite.
      if (e.isConflict) {
        toast("Something changed while deleting — reload and try again.", true);
        return;
      }
      toast(e.message || "Could not delete the scene.", true);
    }
  }

  // Deleting a scene a thread still lists means editing that thread, so the
  // threads are named before it happens rather than after.
  async function offerDetach(event, plotlineIds) {
    const threads = await Promise.all(plotlineIds.map(loadThread));
    const emptied = threads.filter((t) => t.events.length === 1 && t.events[0] === event.id);
    if (emptied.length) return refuseWouldEmpty(event, emptied);
    confirmModal(
      "Other threads use this scene",
      el("div", {}, [
        el("p", { text: "These plotlines list it, and will be edited to drop it:" }),
        el("div", { class: "chip-row" },
          threads.map((t) => el("span", { class: "chip", text: t.title || t.id }))),
        el("p", { text: "The rest of each thread is left exactly as it is." }),
      ]),
      { yes: "Remove it and delete", danger: true, onYes: () => remove(event, true) },
    );
  }

  // The one case the browser refuses rather than offers. A plotline needs at
  // least one scene, and the detach path writes the thread without going through
  // that rule -- so removing a thread's *only* scene would leave it empty, and
  // an empty thread is refused by every later save. The writer would be left
  // with something they could look at and never fix. Cheaper to say so, and name
  // the two ways out.
  function refuseWouldEmpty(event, emptied) {
    const dialog = modal("That would leave a thread with no scenes", el("div", {}, [
      el("p", { text: `“${event.title || event.id}” is the only scene in:` }),
      el("div", { class: "chip-row" },
        emptied.map((t) => el("span", { class: "chip", text: t.title || t.id }))),
      el("p", { text:
        "A plotline needs at least one scene, so dropping this one would leave a "
        + "thread that cannot be saved again. Give each of those threads another "
        + "scene, or delete them, and then delete this scene." }),
      closeRow(() => dialog.close()),
    ]));
  }

  function explainTerminus(event) {
    const dialog = modal("This scene is the book's ending", el("div", {}, [
      el("p", { text:
        `“${event.title || event.id}” is the scene every plotline in this book is `
        + "expected to reach, so deleting it would leave every thread judged "
        + "against nothing." }),
      el("p", { text:
        "Open a plotline and mark another scene as the ending (✦), then come "
        + "back and delete this one." }),
      closeRow(() => dialog.close()),
    ]));
  }

  function loadThread(id) {
    // A thread we cannot read cannot be checked for emptiness; it is still named
    // in the dialog, and treated as one the deletion would not empty.
    return api.getPlotline(book, id).catch(() => ({ id, title: id, events: [] }));
  }

  // -- filtering -------------------------------------------------------------

  let debounce = null;
  filterBox.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.query = filterBox.value.trim();
      state.page = 1;
      render();
    }, 200);
  });

  render();
}

// -- small pieces ------------------------------------------------------------

function breadcrumb(bookTitle, onBooks, onBook) {
  return el("nav", { class: "crumbs" }, [
    el("a", { href: "#/", text: "Books", onclick: (e) => { e.preventDefault(); onBooks(); } }),
    el("span", { class: "sep", text: "›" }),
    el("a", { href: "#/", text: bookTitle, onclick: (e) => { e.preventDefault(); onBook(); } }),
    el("span", { class: "sep", text: "›" }),
    el("span", { text: "Scenes" }),
  ]);
}

// id -> display name for this book's threads. The server caps a page at 100, so
// a book with more threads than that simply shows the remaining ids, which is
// what the column would have shown anyway.
async function loadThreadNames(book) {
  try {
    const data = await api.listPlotlines(book, { perPage: 100 });
    return new Map((data.plotlines || []).map((p) => [p.id, p.name]));
  } catch (e) {
    return new Map();
  }
}

function tool(glyph, title, onclick) {
  return el("button", { class: "icon-btn sm", type: "button", text: glyph, title, onclick });
}

function closeRow(onClose) {
  return el("div", { class: "form-actions" },
    el("button", { class: "btn secondary", type: "button", text: "Close", onclick: onClose }));
}
