// The two upper levels of browsing: pick a world, then pick a category.
//
// Both are the same shape — a grid of cards saying how much is inside — because
// they are the same question asked twice. The home view adds a "recently
// edited" strip, which is the shortest path back to whatever you were writing
// and the reason the app no longer opens on an empty page.

import { api } from "./api.js";
import { clear, el } from "./dom.js";
import { T, count } from "./terms.js";
import { cardGrid, crumbs, timeAgo, viewHead } from "./views.js";

const RECENT_LIMIT = 8;

function loading() {
  return el("p", { class: "muted", text: "Loading…" });
}

function empty(text) {
  return el("p", { class: "empty", text });
}

// -- home: the worlds you can read -------------------------------------------

export async function mountDatabases(container, handlers) {
  clear(container);
  const grid = el("div", {}, [loading()]);
  const recent = el("div", { class: "recent" });
  container.appendChild(el("div", { class: "view" }, [
    viewHead(`Your ${T.database.many}`, [
      { label: `＋ New ${T.database.one}`, onClick: handlers.onCreate },
    ]),
    el("p", { class: "view-lead muted", text:
      `${T.document.Many} live in ${T.collection.many}, and ${T.collection.many} live in a ${T.database.one}. Open one to look inside.` }),
    grid,
    recent,
  ]));

  let databases;
  try { databases = (await api.listDatabases()).databases; }
  catch (e) { clear(grid); grid.appendChild(empty(`Could not load your ${T.database.many}.`)); return; }

  clear(grid);
  if (!databases.length) {
    grid.appendChild(empty(
      `You cannot read any ${T.database.many} yet. Make one to start writing.`));
  } else {
    grid.appendChild(cardGrid(databases.map((db) => ({
      title: db.title,
      // The slug stays on the card: it is what [[links]] point at, and two
      // worlds can read the same once their names are prettied up.
      sub: db.title === db.name ? null : db.name,
      meta: `${count(db.collections, T.collection)} · ${count(db.articles, T.document)}`,
      onOpen: () => handlers.onDatabase(db.name),
    }))));
  }

  await mountRecent(recent, handlers);
}

// The last few articles anyone wrote to, wherever they live. Silent when there
// is nothing yet rather than showing an empty box on a brand-new install.
async function mountRecent(container, handlers) {
  let documents;
  try { documents = (await api.recent(RECENT_LIMIT)).documents; }
  catch (e) { return; }
  if (!documents.length) return;

  clear(container);
  container.appendChild(el("h2", { class: "section-title", text: "Recently edited" }));
  container.appendChild(el("div", { class: "recent-list" }, documents.map((doc) =>
    el("button", {
      class: "recent-row", type: "button",
      onclick: () => handlers.onArticle({ db: doc.database, col: doc.collection, id: doc.id }),
    }, [
      el("span", { class: "recent-title", text: doc.title || doc.id }),
      el("span", { class: "recent-scope", text: `${doc.database_title} › ${doc.collection_title}` }),
      el("span", { class: "recent-when", text: timeAgo(doc.updated) }),
    ]))));
}

// -- one world: the categories inside it -------------------------------------

export async function mountCollections(container, database, handlers) {
  clear(container);
  const grid = el("div", {}, [loading()]);
  const actions = el("div", { class: "view-actions" });
  // The readable name comes back with the listing. Until it does the slug
  // stands in, which is what the address bar says anyway — so the page never
  // flashes an empty heading.
  const crumbBar = el("div", {});
  const heading = el("h1", { class: "view-title", text: database });
  const showCrumbs = (label) => {
    clear(crumbBar);
    crumbBar.appendChild(crumbs([
      { label: "Home", onClick: handlers.onHome },
      { label },
    ]));
  };
  showCrumbs(database);

  container.appendChild(el("div", { class: "view" }, [
    crumbBar,
    el("div", { class: "view-head" }, [heading, actions]),
    grid,
  ]));
  actions.appendChild(el("button", {
    class: "btn sm", type: "button", text: `＋ New ${T.collection.one}`,
    onclick: () => handlers.onCreate(database),
  }));

  let body;
  try { body = await api.listCollections(database); }
  catch (e) { clear(grid); grid.appendChild(empty(`Could not load this ${T.database.one}.`)); return; }

  const collections = body.collections;
  heading.textContent = body.title;
  showCrumbs(body.title);
  clear(grid);
  if (!collections.length) {
    // Two different nothings. `empty` is the server's word for "there is really
    // nothing here"; an empty *list* on its own usually means the categories
    // exist and you may not read them, and offering to delete then would be a
    // lie — the server would refuse anyway.
    grid.appendChild(empty(body.empty
      ? `Nothing in here yet. Add a ${T.collection.one} — characters, locations, lore…`
      : `Nothing in here you can read. Ask whoever owns this ${T.database.one} to share a ${T.collection.one} with you.`));
    if (body.empty) {
      actions.appendChild(el("button", {
        class: "btn sm danger", type: "button", text: `Delete ${T.database.one}`,
        onclick: () => handlers.onDeleteDatabase(database),
      }));
    }
    return;
  }
  grid.appendChild(cardGrid(collections.map((col) => ({
    title: col.title,
    sub: col.title === col.name ? null : col.name,
    meta: count(col.articles, T.document),
    onOpen: () => handlers.onCollection(database, col.name),
  }))));
}
