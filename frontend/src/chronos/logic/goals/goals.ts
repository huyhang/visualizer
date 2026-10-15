// How the goals screen reads the book's goals: which order the cards go in,
// what a filter keeps, what a selected goal pulls into focus, and the one or
// two lines a diagram box has room for. Pure; the server decides every state.

import type { Goal } from "../../api/types";

/** Anything with the two ends of a dependency edge. */
export interface GoalEdgeLike {
  from: string;
  to: string;
}

/**
 * The cards in the order the diagram reads: prerequisites first, then what
 * rests on them. A reader scrolling should meet a goal after the goals it
 * depends on, not after whichever slug happens to sort earlier.
 */
export function inReadingOrder<T extends Pick<Goal, "depth" | "title">>(goals: T[]): T[] {
  return [...goals].sort((a, b) => a.depth - b.depth || a.title.localeCompare(b.title));
}

/** Whether `goal` contains every typed word, in its title, id or description. */
export function matchesFilter(
  goal: Pick<Goal, "id" | "title" | "description">,
  query: string,
): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const text = `${goal.title} ${goal.id} ${goal.description ?? ""}`.toLowerCase();
  return words.every((word) => text.includes(word));
}

export interface Lineage {
  /** Everything the goal rests on, however far up. */
  ancestors: Set<string>;
  /** Everything resting on it, however far down. */
  descendants: Set<string>;
}

function walk(start: string, next: (id: string) => string[]): Set<string> {
  const seen = new Set<string>();
  const queue = [...next(start)];
  while (queue.length) {
    const id = queue.shift() as string;
    if (seen.has(id) || id === start) continue;
    seen.add(id);
    queue.push(...next(id));
  }
  return seen;
}

/** What a selected goal brings into focus on the diagram. Survives a loop in bad data. */
export function lineage(
  goals: Pick<Goal, "id" | "depends_on">[],
  selected: string,
): Lineage {
  const up = new Map(goals.map((g) => [g.id, g.depends_on ?? []]));
  const down = new Map<string, string[]>();
  for (const g of goals)
    for (const d of g.depends_on ?? []) down.set(d, [...(down.get(d) ?? []), g.id]);
  return {
    ancestors: walk(selected, (id) => up.get(id) ?? []),
    descendants: walk(selected, (id) => down.get(id) ?? []),
  };
}

/** Whether an edge lies on the selected goal's chain, upward or downward. */
export function edgeOnChain(
  edge: GoalEdgeLike,
  selected: string,
  { ancestors, descendants }: Lineage,
): boolean {
  const up = (ancestors.has(edge.to) || edge.to === selected) && ancestors.has(edge.from);
  const down =
    (descendants.has(edge.from) || edge.from === selected) && descendants.has(edge.to);
  return up || down;
}

/** Whether a goal stays bright while another is selected. */
export function inFocus(
  id: string,
  selected: string | null,
  chain: Lineage | null,
): boolean {
  if (!selected || !chain) return true;
  return id === selected || chain.ancestors.has(id) || chain.descendants.has(id);
}

export const STATE_WORDS: Record<Goal["status"]["state"], string> = {
  achieved: "achieved",
  open: "open",
  conflicted: "needs attention",
};

/**
 * The line under a box's name: the scene it lands on when it has one, because
 * that is what a writer looks for; the state otherwise.
 */
export function boxSubtitle(goal: Pick<Goal, "status" | "achieved_scene">): string {
  if (goal.status.state === "conflicted") return "needs attention";
  if (goal.achieved_scene) return `✓ ${goal.achieved_scene.title}`;
  return "no scene yet";
}

/** And under that, when -- trimmed to its start, the end a reader orders by. */
export function boxWhen(goal: Pick<Goal, "achieved_scene">): string {
  const when = goal.achieved_scene?.when;
  return when ? (when.split(" → ")[0] ?? "") : "";
}

/** The one line a closed card shows: where it lands. */
export function summaryLine(goal: Pick<Goal, "achieved_scene">): string {
  return goal.achieved_scene ? goal.achieved_scene.title : "no scene yet";
}

/** The delivering scene with its date, in full. */
export function whenLine(goal: Pick<Goal, "achieved_scene">): string | null {
  const scene = goal.achieved_scene;
  if (!scene) return null;
  return scene.when ? `${scene.title} · ${scene.when}` : scene.title;
}
