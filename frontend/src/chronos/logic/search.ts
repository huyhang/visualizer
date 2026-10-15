// How the command palette ranks what it offers against what was typed.
//
// Forgiving on purpose: every typed word must appear in the label (or its
// hint), in any order, and a word that starts a word in the label counts for
// more than one buried inside it. "har ex" finds "The Harbor Exchange".

export interface Searchable {
  label: string;
  hint?: string;
}

const words = (text: string) => text.toLowerCase().split(/\s+/).filter(Boolean);

/** How well `item` answers `query`: 0 when it does not, higher when it does better. */
export function score(item: Searchable, query: string): number {
  const typed = words(query);
  if (typed.length === 0) return 1;
  const label = item.label.toLowerCase();
  const hint = (item.hint ?? "").toLowerCase();
  let total = 0;
  for (const word of typed) {
    const at = label.indexOf(word);
    if (at === 0) total += 4;
    else if (at > 0 && /\W/.test(label[at - 1] ?? "")) total += 3;
    else if (at > 0) total += 1;
    else if (hint.includes(word)) total += 0.5;
    else return 0;
  }
  return total;
}

/** The items that answer `query`, best first; ties keep the order they came in. */
export function rank<T extends Searchable>(items: T[], query: string, limit = 50): T[] {
  return items
    .map((item, n) => ({ item, n, s: score(item, query) }))
    .filter((r) => r.s > 0)
    .sort((a, b) => b.s - a.s || a.n - b.n)
    .slice(0, limit)
    .map((r) => r.item);
}
