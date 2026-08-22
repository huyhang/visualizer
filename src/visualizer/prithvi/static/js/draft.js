// The unsaved edit. Pure functions over two immutable lists: `saved` (what the
// server last told us) and `draft` (what the writer has done since).
//
// Placing, dragging and removing a pin all change only `draft`. Save diffs the
// two and issues the minimum set of writes; Cancel throws `draft` away. Keeping
// that as arithmetic over arrays -- no fetch, no DOM -- is what lets the whole
// staging model be tested from pytest through node.
//
// One subtlety worth stating, because it decides which HTTP verb runs. A pin
// removed from the draft and then placed again still *exists on the server*, so
// it is a move (PUT with the rev we loaded), not a create. The diff works that
// out from key membership rather than from a history of what the writer did,
// which is why "remove it, put it back somewhere else" needs no special case.

// A pin is identified by (collection, article) -- the pair the API keys on.
// Joined with an escaped NUL rather than a printable separator because
// `validate_article_address` bounds the *length* of those two strings but not
// their alphabet: with any character a writer could type, ("a b", "c") and
// ("a", "b c") would collide into one key.
export function pinKey(pin) {
  return `${pin.article.collection}\u0000${pin.article.id}`;
}

export function clonePins(pins) {
  return pins.map((pin) => ({
    ...pin,
    article: { ...pin.article },
    position: { ...pin.position },
  }));
}

export function placePin(draft, saved, { world, map, article, position }) {
  const key = pinKey({ article });
  if (draft.some((pin) => pinKey(pin) === key)) return draft;
  const existing = saved.find((pin) => pinKey(pin) === key);
  const placed = existing
    ? { ...existing, article: { ...existing.article }, position: { ...position } }
    : {
        world,
        map,
        article: { ...article, database: world, status: "available" },
        position: { ...position },
        // No revision yet: this pin has never been written, which is exactly
        // what marks it a create when the diff runs.
        rev: null,
      };
  return [...draft, placed];
}

export function movePin(draft, target, position) {
  const key = pinKey(target);
  return draft.map((pin) => (
    pinKey(pin) === key ? { ...pin, position: { ...position } } : pin
  ));
}

export function removePin(draft, target) {
  const key = pinKey(target);
  return draft.filter((pin) => pinKey(pin) !== key);
}

export function pinChanges(saved, draft) {
  const before = new Map(saved.map((pin) => [pinKey(pin), pin]));
  const after = new Map(draft.map((pin) => [pinKey(pin), pin]));
  return {
    created: draft.filter((pin) => !before.has(pinKey(pin))),
    moved: draft.filter((pin) => {
      const original = before.get(pinKey(pin));
      return Boolean(original) && !samePosition(original.position, pin.position);
    }),
    deleted: saved.filter((pin) => !after.has(pinKey(pin))),
  };
}

export function changeCount(saved, draft) {
  const changes = pinChanges(saved, draft);
  return changes.created.length + changes.moved.length + changes.deleted.length;
}

export function samePin(left, right) {
  return Boolean(left) && Boolean(right) && pinKey(left) === pinKey(right);
}

export function samePosition(left, right) {
  return left.x === right.x && left.y === right.y;
}
