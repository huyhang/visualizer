// The writing page's address: `?book=…&volume=…&section=…&mode=write`, plus
// what it may ask for -- a draft, a block to land on, a panel to open. The same
// query string the old writer took, so every link into it still works.

export type Panel = "akasha" | "coach" | "editor";

export interface Route {
  book: string;
  volume: string;
  section: string;
  draft: string | null;
  block: string | null;
  panel: Panel | null;
}

export function parseRoute(search: string): Route | null {
  const query = new URLSearchParams(search);
  const book = query.get("book");
  const volume = query.get("volume");
  const section = query.get("section");
  if (!book || !volume || !section) return null;
  const asked = query.get("panel");
  // `coach=1` is how the series Review page has always asked for the Coach.
  const panel: Panel | null =
    asked === "akasha" || asked === "coach" || asked === "editor"
      ? asked
      : query.has("coach")
        ? "coach"
        : null;
  return {
    book,
    volume,
    section,
    draft: query.get("draft"),
    block: query.get("block"),
    panel,
  };
}
