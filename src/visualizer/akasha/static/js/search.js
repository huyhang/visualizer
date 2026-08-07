// Detailed search within one category.
//
// The sidebar box is a type-ahead over titles and slugs — fast, but it only
// ever answers "what is this thing called". This view reaches the rest of the
// `/search` endpoint the API has always had: find every article that *mentions*
// something, or every article that *has* a given field (everyone missing a
// birthplace, every location with no ruler).

import { api } from "./api.js";
import { clear, el } from "./dom.js";
import { T } from "./terms.js";
import { crumbs, viewHead } from "./views.js";

// Options are picked by their readable name but carry the slug as their value,
// since the slug is what the endpoint is addressed by.
function select(options, placeholder) {
  return el("select", {}, [
    el("option", { value: "", text: placeholder }),
    ...options.map((o) => el("option", { value: o.name, text: o.title })),
  ]);
}

function field(label, control, hint) {
  return el("div", { class: "field" }, [
    el("label", { text: label }),
    control,
    hint ? el("p", { class: "field-hint muted", text: hint }) : null,
  ]);
}

function resultList(results, where, onArticle) {
  if (!results.length) return el("p", { class: "empty", text: "Nothing matched." });
  return el("div", { class: "result-list" }, results.map((r) =>
    el("button", {
      class: "result-row", type: "button",
      onclick: () => onArticle({ db: where.db, col: where.col, id: r.id }),
    }, [
      el("span", { class: "result-title", text: (r.document || {}).title || r.id }),
      // Readable names for where it lives, but the article's own slug — that is
      // its address, and the reason you might be looking for it.
      el("span", { class: "result-scope", text: `${where.dbTitle} › ${where.colTitle} › ${r.id}` }),
    ])));
}

export async function mountSearch(container, scope, handlers) {
  clear(container);
  const dbHolder = el("div", {});
  const colHolder = el("div", {});
  const textIn = el("input", { type: "search", placeholder: "a word from anywhere in the article" });
  const keyIn = el("input", { type: "text", placeholder: "e.g. race" });
  const results = el("div", {});
  const error = el("p", { class: "form-error" });

  container.appendChild(el("div", { class: "view" }, [
    crumbs([{ label: "Home", onClick: handlers.onHome }, { label: "Search" }]),
    viewHead("Search in detail"),
    el("p", { class: "view-lead muted", text: `Searches every field of every ${T.document.one} in one ${T.collection.one} — not just its title.` }),
    el("div", { class: "search-form" }, [
      field(T.database.One, dbHolder),
      field(T.collection.One, colHolder),
      field("Contains text", textIn),
      field("Has field", keyIn, `Only ${T.document.many} that carry this field at all. Leave blank for any.`),
      el("button", { class: "btn", type: "button", text: "Search", onclick: () => run() }),
      error,
    ]),
    results,
  ]));

  let databases = [];
  try { databases = (await api.listDatabases()).databases; }
  catch (e) { error.textContent = `Could not read your ${T.database.many}.`; return; }

  const dbSelect = select(databases, `Choose a ${T.database.one}…`);
  const has = (list, name) => list.some((entry) => entry.name === name);
  dbSelect.value = scope.db && has(databases, scope.db) ? scope.db : "";
  dbSelect.addEventListener("change", () => loadCollections());
  dbHolder.appendChild(dbSelect);

  let colSelect = select([], `Choose a ${T.database.one} first`);
  colHolder.appendChild(colSelect);

  async function loadCollections() {
    let names = [];
    if (dbSelect.value) {
      try { names = (await api.listCollections(dbSelect.value)).collections; }
      catch (e) { /* an unreadable world simply offers nothing */ }
    }
    const replacement = select(names, names.length ? `Choose a ${T.collection.one}…` : "Nothing to search");
    if (scope.col && has(names, scope.col)) replacement.value = scope.col;
    colHolder.replaceChild(replacement, colSelect);
    colSelect = replacement;
  }
  await loadCollections();

  async function run() {
    error.textContent = "";
    const database = dbSelect.value, collection = colSelect.value;
    if (!database || !collection) { error.textContent = `Choose a ${T.database.one} and a ${T.collection.one}.`; return; }
    // The endpoint needs something to go on; two blank boxes would ask it to
    // return the whole category, which is what the browse list is for.
    if (!textIn.value.trim() && !keyIn.value.trim()) {
      error.textContent = "Enter some text to find, or a field name.";
      return;
    }
    clear(results);
    results.appendChild(el("p", { class: "muted", text: "Searching…" }));
    let found;
    try {
      found = await api.search(database, collection,
        { text: textIn.value.trim(), key: keyIn.value.trim() });
    } catch (e) {
      clear(results);
      error.textContent = e.message || "Could not search.";
      return;
    }
    clear(results);
    results.appendChild(el("p", { class: "muted list-total", text: `${found.count} match${found.count === 1 ? "" : "es"}` }));
    results.appendChild(resultList(found.results, {
      db: database, col: collection,
      dbTitle: dbSelect.selectedOptions[0].text,
      colTitle: colSelect.selectedOptions[0].text,
    }, handlers.onArticle));
  }
}
