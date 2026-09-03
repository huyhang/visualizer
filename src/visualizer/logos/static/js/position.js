// Per-account reading positions kept in this browser. Storage is injected so
// unavailable or corrupt localStorage never prevents a manuscript from opening.

export const POSITION_KEY = "logos-reader-positions";

const keyFor = (username) => `${POSITION_KEY}:${encodeURIComponent(username)}`;
const isText = (value) => typeof value === "string" && value.length > 0;
const finite = (value, fallback) => Number.isFinite(value) ? value : fallback;

function normalise(position) {
  if (!position || !isText(position.volume) || !isText(position.section)) return null;
  return {
    volume: position.volume,
    section: position.section,
    block: isText(position.block) ? position.block : null,
    offset: finite(position.offset, 0),
    progress: Math.min(1, Math.max(0, finite(position.progress, 0))),
  };
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

export function writePosition(storage, username, book, position) {
  const next = normalise(position);
  if (!next) return null;
  const state = readPositions(storage, username);
  state.books[book] = next;
  persist(storage, username, state);
  return next;
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
