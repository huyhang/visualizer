// Where a goal goes on a graph of scenes. Ported from the classic page's
// goalplacing.js: pure, no DOM, no layout.
//
// A goal touches the timeline at one point -- the scene that delivers it -- so
// placing goals asks one question of each: is that scene drawn here? There are
// three ways for the answer to be no, and they are not the same thing, so this
// returns the marks *and* what could not be marked. A graph that dropped the
// unplaced ones would lie: a thread pursuing four goals and marking one reads
// as a thread with one goal.

import type { GoalRef } from "../api/types";

export const NO_SCENE = "no-scene";
export const ELSEWHERE = "elsewhere";
export const MISSING = "missing";
export type UnplacedReason = typeof NO_SCENE | typeof ELSEWHERE | typeof MISSING;

export interface UnplacedGoal {
  id: string;
  title: string;
  reason: UnplacedReason;
  note: string;
}

export interface Placement {
  marks: Map<string, GoalRef[]>;
  unplaced: UnplacedGoal[];
}

/** Which scenes each drawn node stands for. */
export type Coverage = [string, string[]][];

/** A node covering exactly itself: one scene per node, as on a thread's timeline. */
export const eachAlone = (sceneIds: Iterable<string>): Coverage =>
  [...sceneIds].map((id) => [id, [id]]);

/** On the story map a folded band stands for every scene inside it. */
export function coverageOf(
  nodes: { id: string; is_band?: boolean; events?: string[] }[],
): Coverage {
  return nodes.map((n) => [n.id, n.is_band ? [...(n.events ?? [])] : [n.id]]);
}

/** The goals the shown threads pursue. */
export function pursuedBy(lanes: { goals?: string[] }[]): Set<string> {
  return new Set(lanes.flatMap((lane) => lane.goals ?? []));
}

/**
 * The "not landed here" strip: unplaced goals the shown threads actually
 * pursue. Naming every goal in the book that is off screen would make the
 * strip longer the fewer threads you show, which is backwards.
 */
export function stripFor(placed: Placement, lanes: { goals?: string[] }[]): UnplacedGoal[] {
  const pursued = pursuedBy(lanes);
  return placed.unplaced.filter((g) => pursued.has(g.id));
}

/** Why a goal is not on the graph, in the words the strip shows. */
export function unplacedNote(ref: GoalRef, reason: UnplacedReason): string {
  if (reason === MISSING) return "no longer in this book";
  if (reason === NO_SCENE) return "no scene yet";
  const scene = ref.achieved_scene;
  if (!scene) return "delivered by a scene that is no longer in the book";
  return scene.when
    ? `delivered at ${scene.title} · ${scene.when}`
    : `delivered at ${scene.title}`;
}

export function placeGoals(refs: GoalRef[], coverage: Coverage): Placement {
  const nodeOf = new Map<string, string>();
  for (const [node, scenes] of coverage)
    for (const scene of scenes) nodeOf.set(scene, node);
  const marks = new Map<string, GoalRef[]>();
  const unplaced: UnplacedGoal[] = [];
  const miss = (ref: GoalRef, reason: UnplacedReason) =>
    unplaced.push({
      id: ref.id,
      title: ref.title,
      reason,
      note: unplacedNote(ref, reason),
    });

  for (const ref of refs) {
    if (ref.missing) miss(ref, MISSING);
    else if (!ref.achieved_at) miss(ref, NO_SCENE);
    else {
      const node = nodeOf.get(ref.achieved_at);
      if (node === undefined) miss(ref, ELSEWHERE);
      else marks.set(node, [...(marks.get(node) ?? []), ref]);
    }
  }
  return { marks, unplaced };
}

/** Whether anything needs the strip at all. */
export const anyUnplaced = (placed: Placement) => placed.unplaced.length > 0;
