// The scene form: write a new scene, or fix an existing one's timing/place
// without leaving the plotline you are editing. It is one form used both ways —
// a mis-timed scene is the most common cause of a conflict, so the editor has to
// be able to correct it where the conflict is shown.
//
// Referenced characters, items and places are Akasha articles: Chronos never
// invents them, so every reference is chosen from a picker that searches the
// real canon (proxied same-origin) rather than typed free-hand.

import { api } from "./api.js";
import { eventTimeframe } from "./cards.js";
import { clear, el, field, toast } from "./dom.js";
import { entityTitle } from "./entities.js";
import { suggestBox } from "./picker.js";
import { sceneTiming } from "./scenetiming.js";
import { slugify } from "./shared/slug.js";

// The conventional collection each field draws from. A book may name its
// collections anything, so a field can also search the *unconventional* ones it
// observes -- but never another field's (see collectionOptions).
const ROLE_COLLECTION = { location: "locations", characters: "characters", items: "items" };

const MAX_ID_ATTEMPTS = 20;

// A scene is created *at* its id, so unlike a book or a plotline it cannot fall
// back on refusing an empty one -- there is always a name to write it under.
const FALLBACK_SCENE_ID = "scene";

// Turn a saved event response into the lightweight row the editor lists.
export function eventRow(event) {
  return {
    id: event.id,
    title: event.title || event.id,
    when: eventTimeframe(event),
    scheduled: event.scheduled,
    start_tick: event.start_tick,
    end_tick: event.end_tick,
    location: event.location.id,
  };
}

// A chosen article, shown as a removable chip. An existing scene's references
// arrive as bare ids, so the chip shows the id and swaps in the article's title
// once the (memoised) proxy answers -- the same trick the event cards use.
function refChip(book, ref, onRemove) {
  const name = el("span", { text: ref.title || ref.id });
  if (!ref.title) entityTitle(book, ref).then((title) => { name.textContent = title; });
  return el("span", { class: "ref-chip" }, [
    name,
    onRemove ? el("button", {
      class: "ref-remove", type: "button", text: "✕",
      title: "Remove", onclick: onRemove,
    }) : null,
  ]);
}

// A field that chooses one or more Akasha articles.
//   multiple: false -> replaces the choice; true -> appends to a list.
function refField(book, { role, scope, multiple, initial = [], label, hint }) {
  const chosen = initial.slice();
  const chips = el("div", { class: "ref-chips" });
  const collections = collectionOptions(scope, role);
  // Only offer the chooser when this book keeps more than one collection this
  // field could legitimately draw from; otherwise it is a control whose only
  // possible use is to pick the wrong kind of thing.
  const single = collections.length === 1;
  const collection = single
    ? el("span", { class: "ref-collection static muted", text: collections[0] })
    : el("select", { class: "ref-collection", title: "Which collection to search" },
      collections.map((c) => el("option", { value: c, text: c })));
  if (!single) collection.value = collections[0];
  const searched = () => (single ? collections[0] : collection.value);

  const paint = () => {
    clear(chips);
    for (const ref of chosen) {
      chips.appendChild(refChip(book, ref, () => {
        chosen.splice(chosen.indexOf(ref), 1);
        paint();
      }));
    }
    if (!chosen.length) chips.appendChild(el("span", { class: "muted", text: "None chosen." }));
  };

  const picker = suggestBox({
    placeholder: "Search the canon…",
    // Wait for the writer's attention before searching: three fields opening
    // three dropdowns (and three requests) over an empty form is noise, and two
    // of the three are usually not the field being filled in.
    autoSearch: false,
    search: (q) => api.searchEntities(book, { q, collection: searched() })
      .then((r) => r.results),
    renderItem: (item) => [
      el("span", { class: "suggest-title", text: item.title }),
      el("span", { class: "suggest-sub muted", text: `${item.collection} / ${item.id}` }),
    ],
    // An empty picker means two different things. Usually: nothing matched, go
    // write the article. But a book with no declared world *and* nothing to
    // infer one from has nowhere to search at all, and the fix is one screen
    // away rather than in Articles. (A book from before the field existed still
    // infers a scope from its scenes, so it gets the ordinary message.)
    empty: scope.world || scope.collections.length
      ? "No article matches — create it in Articles first."
      : "This book has no world set, so there is nothing to search. Choose one "
        + "with ✎ beside the book's title.",
    onPick: (item) => {
      const ref = { database: item.database, collection: item.collection, id: item.id, title: item.title };
      if (multiple) {
        if (!chosen.some((c) => c.id === ref.id && c.collection === ref.collection)) chosen.push(ref);
      } else {
        chosen.splice(0, chosen.length, ref);
      }
      paint();
    },
  });
  if (!single) collection.addEventListener("change", picker.refresh);
  // ...but once focused, show what is on offer without making them type.
  let primed = false;
  picker.input.addEventListener("focus", () => {
    if (primed) return;
    primed = true;
    picker.refresh();
  });

  paint();
  return {
    node: field(label, el("div", { class: "ref-field" }, [chips, el("div", { class: "ref-search" }, [collection, picker.el])]), hint),
    value: () => chosen.map(({ database, collection: col, id }) => ({ database, collection: col, id })),
  };
}

// Which collections this field may search. A book is free to name its
// collections anything, so the writer can switch -- but never to a collection
// that belongs to a *different* field, or the Place picker would happily let
// you file a character as the location.
function collectionOptions(scope, role) {
  const mine = ROLE_COLLECTION[role];
  const others = Object.entries(ROLE_COLLECTION)
    .filter(([r]) => r !== role)
    .map(([, c]) => c);
  const observed = (scope.collections || []).filter((c) => !others.includes(c));
  return Array.from(new Set([mine, ...observed]));
}

// event === null -> create a scene; otherwise edit that one.
// `calendars` is the book's attachments and `calendarId` which to start in; the
// timing section lets the writer switch between them and reports back which one
// the timeframe was typed in, so the save resolves it the same way the form
// previewed it.
// onSaved(row, event) receives the picker row and the full saved event.
export function sceneForm(book, {
  scope, calendars = [], calendarId = null, event = null, onSaved, onCancel,
}) {
  const editing = event !== null;
  const title = el("input", { type: "text", value: editing ? (event.title || "") : "", placeholder: "The Harbor Exchange" });
  const idBox = el("input", { type: "text", value: editing ? event.id : "", placeholder: "harbor-exchange", disabled: editing ? "" : null });
  const description = el("textarea", { rows: "3", placeholder: "What happens here (optional)" });
  if (editing && event.description) description.value = event.description;

  // The id follows the title until the writer takes it over — ids are permanent,
  // so a new scene gets a sensible one for free without hiding it.
  let idTouched = editing;
  idBox.addEventListener("input", () => { idTouched = true; });
  title.addEventListener("input", () => { if (!idTouched) idBox.value = slugify(title.value); });

  const location = refField(book, {
    role: "location", scope, multiple: false, label: "Place",
    initial: editing ? [event.location] : [],
    hint: "Where the scene happens. Required.",
  });
  const characters = refField(book, {
    role: "characters", scope, multiple: true, label: "Characters",
    initial: editing ? event.characters.slice() : [],
    hint: "Who is present. Two scenes that share a character, at different places, at overlapping times, are a conflict.",
  });
  const items = refField(book, {
    role: "items", scope, multiple: true, label: "Items",
    initial: editing ? event.items.slice() : [],
  });

  const timing = sceneTiming(book, { calendars, calendarId, event });

  const error = el("p", { class: "form-error", hidden: "" });
  const fail = (message) => { error.textContent = message; error.hidden = false; return null; };

  function payload() {
    error.hidden = true;
    const place = location.value()[0];
    if (!place) return fail("Choose where this scene happens.");
    const when = timing.timeframe();
    if (when.error) return fail(when.error);
    return {
      calendar: when.calendar,
      body: {
        title: title.value.trim() || null,
        location: place,
        ...when.body,
        description: description.value,
        characters: characters.value(),
        items: items.value(),
      },
    };
  }

  const save = el("button", { class: "btn", type: "submit", text: editing ? "Save scene" : "Create scene" });

  const form = el("form", { class: "scene-form", onsubmit: async (e) => {
    e.preventDefault();
    const written = payload();
    if (!written) return;
    const { body, calendar } = written;
    save.disabled = true;
    try {
      const saved = editing
        ? await api.updateEvent(book, event.id, body, event.rev, { calendar })
        : await createWithFreeId(
          book, idBox.value.trim() || slugify(title.value) || FALLBACK_SCENE_ID,
          body, calendar,
        );
      onSaved(eventRow(saved), saved);
    } catch (err) {
      fail(err.message || "Could not save the scene.");
      if (err.isConflict) toast("This scene changed elsewhere — reopen it and try again.", true);
    } finally {
      save.disabled = false;
    }
  } }, [
    field("Title", title, "What you will recognise it by in the timeline."),
    field("Id", idBox, editing ? "A scene's id is permanent." : "Used in links and in the API. Derived from the title until you change it."),
    location.node,
    timing.node,
    characters.node,
    items.node,
    field("What happens", description),
    error,
    el("div", { class: "form-actions" }, [
      save,
      el("button", { class: "btn secondary", type: "button", text: "Cancel", onclick: onCancel }),
    ]),
  ]);
  return form;
}

// Ids are unique per book; rather than refuse a duplicate title, take the next
// free suffix — the writer is naming a scene, not choosing a primary key.
async function createWithFreeId(book, baseId, body, calendar) {
  for (let n = 1; n <= MAX_ID_ATTEMPTS; n++) {
    const id = n === 1 ? baseId : `${baseId}-${n}`;
    try {
      return await api.createEvent(book, id, body, { calendar });
    } catch (err) {
      if (err.code !== "ALREADY_EXISTS") throw err;
    }
  }
  throw new Error(`Could not find a free id starting from '${baseId}'.`);
}

// The Akasha scope this book's scenes live in (which database, which
// collections). Fetched once per editor session; falls back to the conventions.
export async function loadScope(book, bookMeta = {}) {
  // `world` is what the book *declared*; `database` is what the server actually
  // searches, which for a book written before the field existed is still the
  // old guess from its scenes. Keeping both lets the picker tell "nothing
  // matches" apart from "there is nowhere to look".
  const world = bookMeta.world || null;
  try {
    const probe = await api.searchEntities(book, { q: "", collection: ROLE_COLLECTION.characters });
    return { database: probe.database, collections: probe.collections, world };
  } catch (e) {
    return { database: world || book, collections: Object.values(ROLE_COLLECTION), world };
  }
}
