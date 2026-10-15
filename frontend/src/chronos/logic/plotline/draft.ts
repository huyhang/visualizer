// A thread as the editor holds it while it is being written: every field the
// save will send, in one value, so undo can step back through all of it at
// once and a preview can be asked for exactly what is on screen.

import type { Plotline, PlotlineWrite } from "../../api/types";
import { idProblem } from "../ids";

export interface ThreadDraft {
  id: string;
  title: string;
  overview: string;
  goals: string[];
  /** The thread's own scenes, in order. Inherited ones come from the continuation. */
  events: string[];
  continuesInto: string | null;
  /** The target's name, for the chip only: never sent, the server derives it. */
  continuesIntoTitle: string | null;
  /** The scene on the target's path this thread joins at; null is its start. */
  continuesIntoAt: string | null;
}

export function emptyDraft(): ThreadDraft {
  return {
    id: "",
    title: "",
    overview: "",
    goals: [],
    events: [],
    continuesInto: null,
    continuesIntoTitle: null,
    continuesIntoAt: null,
  };
}

export function draftFrom(plotline: Plotline): ThreadDraft {
  return {
    id: plotline.id,
    title: plotline.title ?? "",
    overview: plotline.overview ?? "",
    goals: [...plotline.goals],
    events: [...plotline.events],
    continuesInto: plotline.continues_into ?? null,
    continuesIntoTitle: plotline.continues_into_title ?? null,
    continuesIntoAt: plotline.continues_into_at ?? null,
  };
}

/**
 * What a save sends. A *full replace*: whatever this omits is erased, so the
 * overview -- the field nothing recomputes -- must always ride along.
 */
export function bodyOf(draft: ThreadDraft): PlotlineWrite {
  return {
    title: draft.title.trim() || undefined,
    overview: draft.overview,
    events: draft.events,
    goals: draft.goals,
    continues_into: draft.continuesInto,
    continues_into_at: draft.continuesIntoAt,
  };
}

/** What the preview judges: the body, plus the id so findings can name the thread. */
export function candidateOf(draft: ThreadDraft, order: string[] = draft.events) {
  return { ...bodyOf({ ...draft, events: order }), id: draft.id || undefined };
}

/**
 * Only what changes a verdict: a retitled thread does not need re-judging. The
 * id does -- a continuation can loop back to it -- and a new thread's id
 * follows its title until the writer takes it over.
 */
export function candidateKey(draft: ThreadDraft, order: string[] = draft.events): string {
  return JSON.stringify([
    draft.id,
    order,
    draft.goals,
    draft.continuesInto,
    draft.continuesIntoAt,
  ]);
}

/** Why the draft cannot be saved yet, in the writer's words. */
export function draftProblems(
  draft: ThreadDraft,
  creating: boolean,
  taken: Iterable<string> = [],
): string[] {
  const problems: string[] = [];
  if (creating) {
    const id = idProblem(draft.id, taken);
    if (id) problems.push(id);
  }
  if (!draft.events.length) problems.push("A thread needs at least one scene of its own.");
  return problems;
}

/** Point the thread at another one. The join scene belongs to the old target, so it goes. */
export function continueInto(
  draft: ThreadDraft,
  id: string | null,
  title: string | null = null,
): ThreadDraft {
  return {
    ...draft,
    continuesInto: id,
    continuesIntoTitle: id ? title : null,
    continuesIntoAt: null,
  };
}

export function sameDraft(a: ThreadDraft, b: ThreadDraft): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
