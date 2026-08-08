// Readable names for a world and a category, for the surfaces that only know
// the slugs.
//
// An article page arrives from a URL, not from a listing, so it has
// `ember-pact/houses` and nothing else — while every browse page was handed
// `database_title` and `collection_title` by the response that filled it. This
// closes that gap with one cached request rather than a second copy of
// `derive_title` in the browser, which is the duplication `labels.py` exists to
// avoid.
//
// Memoised for the page's lifetime — the same cache-and-fetch shape `links.js`
// uses for wikilink targets — and falls back to the slug, which is what these
// surfaces showed before and is never wrong, only plainer.

import { api } from "./api.js";

const cache = new Map(); // database -> Promise<{ database, collections: Map }>

function load(database) {
  if (!cache.has(database)) {
    cache.set(database, api.listCollections(database)
      .then((body) => ({
        database: body.title || database,
        collections: new Map(body.collections.map((c) => [c.name, c.title])),
      }))
      .catch(() => ({ database, collections: new Map() })));
  }
  return cache.get(database);
}

export async function titlesFor(database, collection) {
  const known = await load(database);
  return {
    database: known.database,
    collection: known.collections.get(collection) || collection,
  };
}

/** Forget everything: a namespace has been created or removed under us. */
export function forgetTitles() {
  cache.clear();
}
