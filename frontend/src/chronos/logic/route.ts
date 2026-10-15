// Where the workspace is, read from and written to the address bar's hash.
//
// The addresses are the classic visualiser's, unchanged, so a link anyone has
// saved or sent opens the same place in either page:
//
//   #/                         the books
//   #/~calendars               the calendar library (not book-scoped)
//   #/<book>                   the book's threads
//   #/<book>/~scenes           its scenes
//   #/<book>/~goals[/<goal>]   its goals, one of them selected
//   #/<book>/~issues           its report
//   #/<book>/~map[/<a,b,c>]    the story map, narrowed to those threads
//   #/<book>/<thread>[/at/<scene>]  one thread, arriving at one scene
//   #/<book>/<thread>/connected[/<scene>]  the map, preset to what meets it
//
// Segments are ids, and an id can never start with `~`, so the reserved names
// cannot collide with a thread.

export type Route =
  | { view: "books" }
  | { view: "calendars" }
  | { view: "threads"; book: string }
  | { view: "scenes"; book: string }
  | { view: "goals"; book: string; goal: string | null }
  | { view: "issues"; book: string }
  | {
      view: "map";
      book: string;
      selection: string[];
      connectedFrom: string | null;
      focusEvent: string | null;
    }
  | { view: "plotline"; book: string; plotline: string; focusEvent: string | null };

export type BookView = Exclude<Route, { view: "books" } | { view: "calendars" }>["view"];

const SCENES = "~scenes";
const GOALS = "~goals";
const ISSUES = "~issues";
const MAP = "~map";
const CALENDARS = "~calendars";

/** One segment, decoded. A malformed escape is kept as typed. */
function decode(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

/** The hash's segments as written, before decoding. */
function rawSegments(hash: string): string[] {
  return hash
    .replace(/^#\/?/, "")
    .split("/")
    .filter((s) => s.length > 0);
}

/** The hash's segments, decoded. */
export function segments(hash: string): string[] {
  return rawSegments(hash).map(decode);
}

function bookRoute(book: string, rest: string[], raw: string[]): Route {
  const [first, second, third] = rest;
  if (first === undefined) return { view: "threads", book };
  if (first === SCENES) return { view: "scenes", book };
  if (first === ISSUES) return { view: "issues", book };
  if (first === GOALS) return { view: "goals", book, goal: second ?? null };
  if (first === MAP) {
    // Split as written, then decode: an id holding a comma is written %2C.
    const selection = (raw[1] ?? "").split(",").filter(Boolean).map(decode);
    return { view: "map", book, selection, connectedFrom: null, focusEvent: null };
  }
  if (second === "connected") {
    return {
      view: "map",
      book,
      selection: [],
      connectedFrom: first,
      focusEvent: third ?? null,
    };
  }
  const focusEvent = second === "at" ? (third ?? null) : null;
  return { view: "plotline", book, plotline: first, focusEvent };
}

export function parseRoute(hash: string): Route {
  const raw = rawSegments(hash);
  const [book, ...rest] = raw.map(decode);
  if (book === undefined) return { view: "books" };
  if (book === CALENDARS) return { view: "calendars" };
  return bookRoute(book, rest, raw.slice(1));
}

const enc = encodeURIComponent;

export function hashFor(route: Route): string {
  switch (route.view) {
    case "books":
      return "#/";
    case "calendars":
      return `#/${CALENDARS}`;
    case "threads":
      return `#/${enc(route.book)}`;
    case "scenes":
      return `#/${enc(route.book)}/${SCENES}`;
    case "issues":
      return `#/${enc(route.book)}/${ISSUES}`;
    case "goals":
      return `#/${enc(route.book)}/${GOALS}` + (route.goal ? `/${enc(route.goal)}` : "");
    case "map":
      if (route.connectedFrom) {
        return (
          `#/${enc(route.book)}/${enc(route.connectedFrom)}/connected` +
          (route.focusEvent ? `/${enc(route.focusEvent)}` : "")
        );
      }
      return (
        `#/${enc(route.book)}/${MAP}` +
        (route.selection.length ? `/${route.selection.map(enc).join(",")}` : "")
      );
    case "plotline":
      return (
        `#/${enc(route.book)}/${enc(route.plotline)}` +
        (route.focusEvent ? `/at/${enc(route.focusEvent)}` : "")
      );
  }
}

/** The book a route is inside, or null outside every book. */
export function bookOf(route: Route): string | null {
  return "book" in route ? route.book : null;
}

// Builders, so callers say where they are going rather than spelling a hash.
export const to = {
  books: (): Route => ({ view: "books" }),
  calendars: (): Route => ({ view: "calendars" }),
  threads: (book: string): Route => ({ view: "threads", book }),
  scenes: (book: string): Route => ({ view: "scenes", book }),
  issues: (book: string): Route => ({ view: "issues", book }),
  goals: (book: string, goal: string | null = null): Route => ({
    view: "goals",
    book,
    goal,
  }),
  map: (book: string, selection: string[] = []): Route => ({
    view: "map",
    book,
    selection,
    connectedFrom: null,
    focusEvent: null,
  }),
  connected: (book: string, plotline: string, focusEvent: string | null = null): Route => ({
    view: "map",
    book,
    selection: [],
    connectedFrom: plotline,
    focusEvent,
  }),
  plotline: (book: string, plotline: string, focusEvent: string | null = null): Route => ({
    view: "plotline",
    book,
    plotline,
    focusEvent,
  }),
};
