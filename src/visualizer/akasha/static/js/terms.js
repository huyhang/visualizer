// What the screen calls the store's three levels.
//
// The API, the URLs and the payloads speak MongoDB — database → collection →
// document — and always will: that triple is the addressing scheme behind every
// grant, every wikilink and every chronos reference. The screen speaks to a
// novelist instead, who has a world with categories of articles in it. Keeping
// the two apart means the UI can be renamed without touching a single route.
//
// The mirror of `terms.py`, which serves the Jinja pages; a test compares them
// so they cannot drift.

export const T = {
  database: { one: "world", many: "worlds", One: "World", Many: "Worlds" },
  collection: { one: "category", many: "categories", One: "Category", Many: "Categories" },
  document: { one: "article", many: "articles", One: "Article", Many: "Articles" },
};

// "1 article" / "4 categories" — the plural is looked up, not guessed at by
// adding an s, which is exactly where "categorys" would have come from.
export function count(n, term) {
  return `${n} ${n === 1 ? term.one : term.many}`;
}
