// Per-account reading positions kept in this browser. Storage is injected so
// unavailable or corrupt localStorage never prevents a manuscript from opening.
//
// Two marks per book, because they answer different questions. `last` is where
// the reader actually is: it carries a block anchor, so reopening that section
// puts the same words back under their eyes. `furthest` is the deepest point
// they have reached, and it is what "Continue reading" offers -- going back to
// check a detail in an early chapter must not throw away your place at the end.

export const POSITION_KEY = "logos-reader-positions";

const keyFor = (username) => `${POSITION_KEY}:${encodeURIComponent(username)}`;
const isText = (value) => typeof value === "string" && value.length > 0;
const finite = (value, fallback) => Number.isFinite(value) ? value : fallback;
const fraction = (value) => Math.min(1, Math.max(0, finite(value, 0)));

/** Where you are: the section, the block under the marker, and how far in. */
function normaliseSpot(spot) {
  if (!spot || !isText(spot.volume) || !isText(spot.section)) return null;
  return {
    volume: spot.volume,
    section: spot.section,
    block: isText(spot.block) ? spot.block : null,
    offset: finite(spot.offset, 0),
    progress: fraction(spot.progress),
  };
}

/** How far you got: no anchor, because it is a milestone and not a place. */
function normaliseMark(mark) {
  if (!mark || !isText(mark.volume) || !isText(mark.section)) return null;
  return {
    volume: mark.volume,
    section: mark.section,
    progress: fraction(mark.progress),
  };
}

function normalise(entry) {
  if (!entry || typeof entry !== "object") return null;
  // Records written before there were two marks are a bare spot: read one as
  // `last`, and take it at its word for `furthest`.
  const last = normaliseSpot(entry.last) || normaliseSpot(entry);
  const furthest = normaliseMark(entry.furthest) || normaliseMark(last);
  if (!last && !furthest) return null;
  return { last, furthest };
}

export function parsePositions(value) {
  const source = value && typeof value === "object" && value.version === 1
    && value.books && typeof value.books === "object" ? value.books : {};
  const books = Object.fromEntries(
    Object.entries(source)
      .map(([book, position]) => [book, normalise(position)])
      .filter(([, position]) => position !== null),
  );
  return { version: 1, books };
}

export function readPositions(storage, username) {
  try {
    return parsePositions(JSON.parse(storage.getItem(keyFor(username))));
  } catch (_error) {
    return { version: 1, books: {} };
  }
}

export function readPosition(storage, username, book) {
  const books = readPositions(storage, username).books;
  return Object.prototype.hasOwnProperty.call(books, book) ? books[book] : null;
}

function persist(storage, username, state) {
  try {
    storage.setItem(keyFor(username), JSON.stringify(state));
  } catch (_error) {
    // Reading still works; only resuming in a later page is unavailable.
  }
  return state;
}

/** Replace one book's two marks with a server-validated entry. */
export function storePosition(storage, username, book, entry) {
  const state = readPositions(storage, username);
  const normalised = normalise(entry);
  if (normalised) state.books[book] = normalised;
  else delete state.books[book];
  persist(storage, username, state);
  return normalised;
}

/**
 * The furthest mark after visiting ``spot``, or the saved one if that is still
 * further on.
 *
 * ``ahead`` says whether the spot names a later section than the saved mark.
 * Book order lives with the caller; this only applies the policy, which is why
 * it can be checked without a manuscript. Within one section the deeper read
 * wins, so reloading a section at the top cannot walk its own progress back.
 */
export function advance(saved, spot, ahead) {
  const mark = normaliseMark(spot);
  if (!mark) return saved || null;
  if (!saved) return mark;
  const here = saved.volume === mark.volume && saved.section === mark.section;
  if (here) return mark.progress > saved.progress ? mark : saved;
  return ahead ? mark : saved;
}

export function writePosition(storage, username, book, spot, ahead = false) {
  const last = normaliseSpot(spot);
  if (!last) return null;
  const state = readPositions(storage, username);
  const held = state.books[book] || null;
  const entry = { last, furthest: advance(held && held.furthest, last, ahead) };
  state.books[book] = entry;
  persist(storage, username, state);
  return entry;
}

export function forgetPosition(storage, username, book) {
  const state = readPositions(storage, username);
  delete state.books[book];
  persist(storage, username, state);
}

export function prunePositions(storage, username, readableBooks) {
  const allowed = new Set(readableBooks);
  const state = readPositions(storage, username);
  state.books = Object.fromEntries(
    Object.entries(state.books).filter(([book]) => allowed.has(book)),
  );
  return persist(storage, username, state);
}

/** Save the paragraph crossing a stable viewport marker, plus its offset. */
export function blockAnchor(blocks, marker) {
  if (!blocks.length) return { block: null, offset: 0 };
  let chosen = blocks[0];
  for (const block of blocks) {
    if (block.top > marker) break;
    chosen = block;
  }
  return { block: chosen.id, offset: marker - chosen.top };
}

export function scrollForAnchor(blockTop, offset, marker) {
  return blockTop + finite(offset, 0) - marker;
}
