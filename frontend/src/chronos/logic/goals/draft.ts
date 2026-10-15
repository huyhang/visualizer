// The goal editor's state and rules, apart from its markup: what a new or
// existing goal starts as, how the id follows the title, what may be offered
// as a prerequisite, what goes over the wire, and how a refusal reads.
//
// Two fields are why goals are records at all: `depends_on` makes them a graph
// rather than a list of labels, and `achieved_at` is the one point where a
// goal touches the timeline.

import { codeOf, evidenceIds, messageOf, ChronosApiError } from "../../api/errors";
import type { Goal, GoalWrite, Named } from "../../api/types";
import { followTitle } from "../ids";

export interface GoalDraft {
  id: string;
  title: string;
  description: string;
  dependsOn: string[];
  achievedAt: string | null;
  /** Shown beside the chosen scene; the picker knows the title, the payload does not. */
  achievedTitle: string | null;
  /** Ids are permanent, so an existing goal's never follows its title. */
  idTakenOver: boolean;
}

export function draftFor(goal: Goal | null): GoalDraft {
  if (!goal) {
    return {
      id: "",
      title: "",
      description: "",
      dependsOn: [],
      achievedAt: null,
      achievedTitle: null,
      idTakenOver: false,
    };
  }
  return {
    id: goal.id,
    title: goal.title ?? "",
    description: goal.description ?? "",
    dependsOn: [...goal.depends_on],
    achievedAt: goal.achieved_at ?? null,
    achievedTitle: goal.achieved_scene?.title ?? null,
    idTakenOver: true,
  };
}

export const withTitle = (draft: GoalDraft, title: string): GoalDraft => ({
  ...draft,
  title,
  id: followTitle(title, draft.id, draft.idTakenOver),
});

export const withId = (draft: GoalDraft, id: string): GoalDraft => ({
  ...draft,
  id: id.trim(),
  idTakenOver: true,
});

/**
 * What a save sends. A full replace: a blank title and an unset scene go as
 * null rather than being left out, so clearing them clears them.
 */
export interface GoalBody extends Omit<GoalWrite, "title" | "achieved_at"> {
  title: string | null;
  achieved_at: string | null;
}

export function goalBody(draft: GoalDraft): GoalBody {
  return {
    title: draft.title.trim() || null,
    description: draft.description,
    depends_on: draft.dependsOn,
    achieved_at: draft.achievedAt,
  };
}

/**
 * The goals that may be offered as prerequisites: never itself, never one
 * already chosen, and never one that already rests on it directly -- the
 * server refuses those as loops. A deeper loop is left to the server, which
 * checks the whole chain.
 */
export function offerable<T extends Pick<Goal, "id" | "title" | "depends_on">>(
  goals: T[],
  draft: Pick<GoalDraft, "id" | "dependsOn">,
  query = "",
): T[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return goals.filter(
    (g) =>
      g.id !== draft.id &&
      !draft.dependsOn.includes(g.id) &&
      !(draft.id && (g.depends_on ?? []).includes(draft.id)) &&
      words.every((w) => `${g.title} ${g.id}`.toLowerCase().includes(w)),
  );
}

/** A refusal from a save, in the writer's words. */
export function saveFailure(error: unknown, id: string): string {
  const code = codeOf(error);
  if (code === "ALREADY_EXISTS")
    return `A goal with the id “${id}” already exists. Choose another.`;
  if (code === "GOAL_CYCLE") {
    const cycle = evidenceIds(error, "cycle");
    return cycle.length
      ? `That would make the goals loop: ${cycle.join(" → ")}.`
      : "That would make the goals loop.";
  }
  if (error instanceof ChronosApiError && error.isConflict) {
    return "Someone else changed this goal since you opened it. Close this and open it again to see their version.";
  }
  return messageOf(error, "Could not save the goal.");
}

export interface Blockers {
  threads: Named[];
  goals: Named[];
}

export const noBlockers = (b: Blockers) => b.threads.length === 0 && b.goals.length === 0;

/** What points at a goal, as the book last told us: the threads serving it and the goals resting on it. */
export function blockersOf(goal: Pick<Goal, "plotlines" | "required_by">): Blockers {
  return {
    threads: goal.plotlines.map((p) => ({ id: p.id, title: p.title || p.id })),
    goals: goal.required_by.map((g) => ({ id: g.id, title: g.title || g.id })),
  };
}

/**
 * What points at it as the server says when it refuses a delete -- the truth
 * when the page was stale. Ids are named through whatever titles are known.
 */
export function blockersFromRefusal(
  error: unknown,
  threadTitle: (id: string) => string | undefined,
  goalTitle: (id: string) => string | undefined,
): Blockers | null {
  if (codeOf(error) !== "GOAL_IN_USE") return null;
  return {
    threads: evidenceIds(error, "plotlines").map((id) => ({
      id,
      title: threadTitle(id) ?? id,
    })),
    goals: evidenceIds(error, "goals").map((id) => ({ id, title: goalTitle(id) ?? id })),
  };
}
