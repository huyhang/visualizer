// Modules both services load. Served by each app under its *own* static path
// (see ``visualizer/shared_assets.py``), so `./shared/slug.js` resolves from
// either tree and at either mount — akasha at `/`, chronos at `/timeline`, or
// each standalone on its own port during development.
//
// Keep this directory small and dependency-free. A module here cannot import
// from either service (there is no bundler and no import map), and anything
// that knows about books or articles belongs in the service that owns them.

// A url-and-api-safe id derived from what someone typed. Both services derive
// ids this way, and an article and the scene that references it should reach
// the same id from the same title — which is exactly what drifted while there
// were two copies of this function.
//
// Returns "" when there is nothing usable. That default is deliberate: a caller
// that can refuse an empty id (a book, a plotline) gets one it can reject,
// while a caller that *must* produce one — an article and a scene are each
// created **at** their id — says so explicitly with its own fallback. Baking a
// fallback in here is how an empty form quietly creates a record called
// "untitled".
export function slugify(text) {
  return String(text || "")
    .toLowerCase()
    // Apostrophes bind to the word, they do not break it: "The Knight's Road"
    // is knights-road, not knight-s-road. Dropped before the split rather than
    // after, or the possessive 's' is stranded as its own segment. Both the
    // typewriter ' and the curly ’ that editors (and macOS) substitute for it.
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
