// Making new things, from wherever you happen to be standing — and removing the
// ones made by mistake.
//
// Every dialog here is *scoped*: it is opened from a page that already knows
// which world and category you are looking at, so it asks only for what it
// cannot know — a name — and offers the existing names for the rest. Nothing
// here creates a namespace as a side effect of being opened: a new article's
// category is created when the article is *saved* (`pendingCollection`), so an
// abandoned dialog leaves nothing behind to clean up.

import { api, ApiError } from "./api.js";
import { clear, el, modal, toast } from "./dom.js";
import { T, count } from "./terms.js";

export function slugify(text) {
  return text.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "untitled";
}

// Characters MongoDB will not take in a name, plus the leading underscore the
// internal stores reserve. Checked here so a typo is answered in the dialog
// rather than by a 400 after the fact.
const BAD_NAME = /[/\\. "$*<>:|?]/;

function nameError(name, what) {
  if (!name) return `Give the ${what} a name.`;
  if (name.startsWith("_")) return "Names starting with “_” are reserved.";
  if (BAD_NAME.test(name)) return `A ${what} name cannot contain spaces or / \\ . " $ * < > : | ?`;
  return null;
}

function field(label, control, hint) {
  return el("div", { class: "field" }, [
    el("label", { text: label }),
    control,
    hint ? el("p", { class: "field-hint muted", text: hint }) : null,
  ]);
}

// -- picking a name that may or may not exist yet ----------------------------

// A chooser over the names that already exist, which can also mint a new one:
// a select of what is there plus a "＋ New…" option that reveals a text box.
// This is the whole point of the redesign — you should never have to remember
// and retype a database name that is sitting in a list beside you.
function namePicker({ names, value, placeholder, onChange = () => {} }) {
  // A sentinel that cannot collide with a real name: MongoDB will not take a
  // `$` in one, and `nameError` refuses it too.
  const NEW = "$new";
  const input = el("input", { type: "text", placeholder });
  // Entries are `{name, title}`: you pick by the readable name, but what comes
  // back is the slug, because that is what the URL and the API are addressed by.
  const select = el("select", {}, [
    ...names.map((n) => el("option", { value: n.name, text: n.title })),
    el("option", { value: NEW, text: "＋ New…" }),
  ]);
  const creating = () => select.value === NEW;
  const sync = () => {
    input.hidden = !creating();
    if (creating()) input.focus();
    onChange();
  };
  select.addEventListener("change", sync);
  input.addEventListener("input", onChange);

  // With nothing to choose from, skip the empty select and just ask for a name.
  if (!names.length) select.value = NEW;
  else if (value && names.some((n) => n.name === value)) select.value = value;
  select.hidden = names.length === 0;
  input.hidden = !creating();

  return {
    el: el("div", { class: "name-picker" }, [select, input]),
    value: () => (creating() ? input.value.trim() : select.value),
    isNew: creating,
  };
}

// Replace a picker in place — used when choosing a database changes which
// collections are on offer.
function refillPicker(holder, options) {
  clear(holder);
  const picker = namePicker(options);
  holder.appendChild(picker.el);
  return picker;
}

// -- slug availability -------------------------------------------------------

async function isTaken(db, col, id) {
  try {
    await api.getDoc(db, col, id);
    return true;
  } catch (e) {
    if (e instanceof ApiError && e.isNotFound) return false;
    // A 403 means the slug belongs to someone else's article, and anything else
    // means we could not find out. Neither is a slug we should hand out.
    return true;
  }
}

// The first unused slug in the `name`, `name-2`, `name-3` … sequence.
async function freeId(db, col, id, tries = 20) {
  for (let n = 1; n <= tries; n++) {
    const candidate = n === 1 ? id : `${id}-${n}`;
    if (!(await isTaken(db, col, candidate))) return candidate;
  }
  return `${id}-${Date.now()}`;
}

// Create an article under the first free slug near `id`, rather than refusing
// because the obvious one is taken. Retries on the 409 itself, so two people
// creating "the-inn" at once both end up with an article.
export async function createWithFreeId(db, col, id, body, tries = 20) {
  for (let n = 1; n <= tries; n++) {
    const candidate = n === 1 ? id : `${id}-${n}`;
    try {
      await api.createDoc(db, col, candidate, body);
      return candidate;
    } catch (e) {
      if (!(e instanceof ApiError && e.isConflict)) throw e;
    }
  }
  throw new Error(`Could not find a free slug near “${id}”.`);
}

// Create a collection, treating "it is already there" as success.
export async function ensureCollection(db, col) {
  try { await api.createCollection(db, col); }
  catch (e) { if (!(e instanceof ApiError && e.status === 409)) throw e; }
}

// -- the dialogs -------------------------------------------------------------

// Title in, slug out — until the writer edits the slug themselves, after which
// it is theirs and we stop touching it.
function linkTitleToSlug(titleIn, slugIn) {
  let touched = false;
  titleIn.addEventListener("input", () => { if (!touched) slugIn.value = slugify(titleIn.value); });
  slugIn.addEventListener("input", () => { touched = true; });
}

export function newDatabaseDialog({ onCreated }) {
  const dbIn = el("input", { type: "text", placeholder: "middle-earth" });
  const colIn = el("input", { type: "text", placeholder: "characters" });
  const error = el("p", { class: "form-error" });

  modal({
    title: `New ${T.database.one}`,
    body: el("div", {}, [
      field(T.database.One, dbIn, "One per story, usually."),
      field(`First ${T.collection.one}`, colIn,
        `A ${T.database.one} has to contain something, so name its first ${T.collection.one}: characters, locations, lore…`),
      error,
    ]),
    actions: [
      { label: "Cancel", variant: "secondary" },
      { label: "Create", variant: "primary", onClick: async (close) => {
          const db = dbIn.value.trim(), col = colIn.value.trim();
          const bad = nameError(db, T.database.one) || nameError(col, T.collection.one);
          if (bad) { error.textContent = bad; return; }
          try { await api.createCollection(db, col); }
          catch (e) { error.textContent = e.message || "Could not create it."; return; }
          toast(`Created “${db}”.`);
          close();
          onCreated(db, col);
        } },
    ],
  });
}

export function newCollectionDialog(database, { onCreated }) {
  const colIn = el("input", { type: "text", placeholder: "locations" });
  const error = el("p", { class: "form-error" });

  modal({
    title: `New ${T.collection.one} in “${database}”`,
    body: el("div", {}, [
      field(T.collection.One, colIn, "A kind of thing: characters, locations, items, lore…"),
      error,
    ]),
    actions: [
      { label: "Cancel", variant: "secondary" },
      { label: "Create", variant: "primary", onClick: async (close) => {
          const col = colIn.value.trim();
          const bad = nameError(col, T.collection.one);
          if (bad) { error.textContent = bad; return; }
          try { await api.createCollection(database, col); }
          catch (e) { error.textContent = e.message || "Could not create it."; return; }
          toast(`Created “${col}”.`);
          close();
          onCreated(col);
        } },
    ],
  });
}

// The general "New article" flow. `scope` is where the writer already is —
// possibly nothing (from the header button), possibly a full world and category
// (from a category page), in which case those fields come pre-answered and all
// that is left is a title.
export async function newArticleDialog(scope, { onOpen }) {
  let databases = [];
  try { databases = (await api.listDatabases()).databases; }
  catch (e) { toast(`Could not read your ${T.database.many}.`, true); return; }

  const dbHolder = el("div", {});
  const colHolder = el("div", {});
  const titleIn = el("input", { type: "text", placeholder: "Aragorn" });
  const slugIn = el("input", { type: "text", placeholder: "aragorn" });
  const error = el("p", { class: "form-error" });
  const note = el("p", { class: "field-hint muted" });
  linkTitleToSlug(titleIn, slugIn);

  const dbPicker = refillPicker(dbHolder, {
    names: databases, value: scope.db, placeholder: `new-${T.database.one}-name`,
    onChange: () => loadCollections(),
  });

  let colPicker = refillPicker(colHolder, { names: [], placeholder: `new-${T.collection.one}-name` });
  let known = [];

  // Which categories are on offer follows which world is chosen; a world that
  // does not exist yet obviously has none.
  async function loadCollections() {
    const db = dbPicker.value();
    known = [];
    if (db && !dbPicker.isNew()) {
      try { known = (await api.listCollections(db)).collections; }
      catch (e) { /* an unreadable world simply offers nothing */ }
    }
    colPicker = refillPicker(colHolder, {
      names: known, value: scope.col, placeholder: `new-${T.collection.one}-name`,
    });
  }
  await loadCollections();

  modal({
    title: `New ${T.document.one}`,
    body: el("div", {}, [
      field(T.database.One, dbHolder),
      field(T.collection.One, colHolder),
      field("Title", titleIn),
      field("Slug (id)", slugIn, "Its permanent address. Links point at this, so it cannot be changed later."),
      note,
      error,
    ]),
    actions: [
      { label: "Cancel", variant: "secondary" },
      { label: "Continue", variant: "primary", onClick: async (close) => {
          const db = dbPicker.value(), col = colPicker.value();
          const bad = nameError(db, T.database.one) || nameError(col, T.collection.one)
            || (slugIn.value.trim() ? null : `Give the ${T.document.one} a slug.`);
          if (bad) { error.textContent = bad; return; }

          // The category is only made once the article is saved, so backing out
          // of the editor leaves no empty namespace behind.
          const pendingCollection = dbPicker.isNew() || !known.some((c) => c.name === col);
          let id = slugify(slugIn.value);
          if (!pendingCollection) {
            const free = await freeId(db, col, id);
            if (free !== id) {
              // Offer the free slug instead of refusing; the writer can still
              // change it before pressing Continue again.
              note.textContent = `“${id}” is taken — using “${free}”.`;
              slugIn.value = free;
              id = free;
            }
          }
          close();
          onOpen({ db, col, id, title: titleIn.value.trim(), pendingCollection });
        } },
    ],
  });
}

// Create-on-the-fly from the link picker: the writer typed [[a name]] that does
// not exist yet. Resolves to the new article's target, or null if they backed
// out — the caller is waiting to decide what to write into the text.
export function createLinkTarget(query, scope) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (value) => { if (!settled) { settled = true; resolve(value); } };
    const slugIn = el("input", { type: "text", value: slugify(query) });
    const colIn = el("input", { type: "text", value: scope.col });
    const error = el("p", { class: "form-error" });

    modal({
      title: `Create “${query}”`,
      body: el("div", {}, [
        field(T.collection.One, colIn, `In ${scope.db}.`),
        field("Slug (id)", slugIn),
        error,
      ]),
      // However this closes — the ✕, Escape, the backdrop — the caller gets an
      // answer, otherwise the editor would wait for ever.
      onClose: () => done(null),
      actions: [
        { label: "Cancel", variant: "secondary" },
        { label: "Create", variant: "primary", onClick: async (close) => {
            const col = colIn.value.trim();
            const bad = nameError(col, T.collection.one);
            if (bad) { error.textContent = bad; return; }
            try {
              await ensureCollection(scope.db, col);
              const id = await createWithFreeId(scope.db, col, slugify(slugIn.value), { title: query });
              toast(`Created “${query}”.`);
              done({ db: scope.db, col, id, title: query });
              close();
            } catch (e) { error.textContent = e.message || "Could not create it."; }
          } },
      ],
    });
  });
}

// -- removing an empty namespace ---------------------------------------------

// `deleted` is how many tombstones the category still holds: articles that were
// deleted from it, whose version history is all that is left. Nothing else can
// be in here — the server refuses while a live article remains — so this dialog
// has exactly one job, which is to be honest about that history before it goes,
// since unlike deleting an article this cannot be undone.
export function confirmDeleteCollection(database, collection, deleted, { onDeleted }) {
  const destructive = deleted > 0;
  const body = el("div", {}, [
    el("p", { text: destructive
      ? `No ${T.document.many} are left in “${collection}”, but the version history of ${count(deleted, T.document)} deleted from it is.`
      : `“${collection}” is empty, so nothing is lost.` }),
    destructive
      ? el("p", { class: "form-error", text: "Deleting it discards that history permanently — it cannot be restored." })
      : null,
    el("p", { class: "muted", text:
      `If this is the only ${T.collection.one} in “${database}”, that ${T.database.one} goes too.` }),
  ]);

  modal({
    title: `Delete “${collection}”?`,
    body,
    actions: [
      { label: "Cancel", variant: "secondary" },
      { label: destructive ? "Delete anyway" : "Delete", variant: "danger", onClick: async (close) => {
          let result;
          try { result = await api.deleteCollection(database, collection, { purge: destructive }); }
          catch (e) { toast(e.message || "Could not delete it.", true); return; }
          toast(`Deleted “${collection}”.`);
          close();
          // The server drops the world along with its last category, so the
          // caller needs to know not to navigate to a page that just vanished.
          onDeleted(Boolean(result && result.database_removed));
        } },
    ],
  });
}

// A safety net rather than a route anyone walks: MongoDB drops a database the
// moment its last collection goes, so a world with nothing in it normally
// cannot exist to be found. This clears one left behind by an older version, or
// by a storage backend that keeps the shell around.
export function confirmDeleteDatabase(database, { onDeleted }) {
  modal({
    title: `Delete “${database}”?`,
    body: el("p", { text:
      `This ${T.database.one} has no ${T.collection.many} left in it, so nothing is lost.` }),
    actions: [
      { label: "Cancel", variant: "secondary" },
      { label: "Delete", variant: "danger", onClick: async (close) => {
          try { await api.deleteDatabase(database); }
          catch (e) { toast(e.message || "Could not delete it.", true); return; }
          toast(`Deleted “${database}”.`);
          close();
          onDeleted();
        } },
    ],
  });
}
