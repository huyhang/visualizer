// Deleting a scene, the only irreversible thing on the Scenes screen. The
// server decides and the browser explains: each refusal becomes a step that
// says what is in the way and what to do about it. Ported from scenes.js.

import type { SceneEvent } from "../../api/types";

export interface ThreadInWay {
  id: string;
  title: string;
  /** The thread's own scenes, as stored -- not the path it inherits. */
  events: string[];
}

export type DeleteStep =
  | { kind: "idle" }
  | { kind: "confirm"; event: SceneEvent }
  | { kind: "detach"; event: SceneEvent; threads: ThreadInWay[] }
  | { kind: "would-empty"; event: SceneEvent; emptied: ThreadInWay[] }
  | { kind: "terminus"; event: SceneEvent };

/** The first step: a scene that is the book's ending is explained, not offered. */
export function firstStep(
  event: SceneEvent,
  terminus: string | null | undefined,
): DeleteStep {
  return event.id === terminus ? { kind: "terminus", event } : { kind: "confirm", event };
}

/**
 * The threads that would be left with no scenes. A thread needs at least one,
 * and detaching writes the thread without that rule -- so removing a thread's
 * only scene would leave it something nobody could ever save again.
 */
export function emptiedBy(threads: ThreadInWay[], scene: string): ThreadInWay[] {
  return threads.filter((t) => t.events.length === 1 && t.events[0] === scene);
}

/** What EVENT_IN_USE leads to: offer to detach, or refuse if that would empty a thread. */
export function afterInUse(event: SceneEvent, threads: ThreadInWay[]): DeleteStep {
  const emptied = emptiedBy(threads, event.id);
  return emptied.length
    ? { kind: "would-empty", event, emptied }
    : { kind: "detach", event, threads };
}

/**
 * Ids to try for a new scene, in order. Ids are unique per book; rather than
 * refuse a duplicate title, take the next free suffix -- the writer is naming
 * a scene, not choosing a primary key.
 */
export function candidateIds(base: string, attempts = 20): string[] {
  return Array.from({ length: attempts }, (_, n) => (n === 0 ? base : `${base}-${n + 1}`));
}

/** Create at the first free id, trying each candidate until one is not taken. */
export async function createAtFreeId<T>(
  base: string,
  create: (id: string) => Promise<T>,
  taken: (error: unknown) => boolean,
  attempts = 20,
): Promise<T> {
  for (const id of candidateIds(base, attempts)) {
    try {
      return await create(id);
    } catch (error) {
      if (!taken(error)) throw error;
    }
  }
  throw new Error(`Could not find a free id starting from '${base}'.`);
}
