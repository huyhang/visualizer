// A note in the margin, whoever wrote it: a Coach finding or an editor's issue.
// The underline, the popover and the panels all speak in notes, so the two
// sources share one way of being shown, accepted and set aside.

import type { CoachIssue, ReviewIssue } from "../api/types";
import { coachAnnotationId, currentFix, editorAnnotationId } from "./review";

export type Note =
  | { source: "coach"; id: string; issue: CoachIssue }
  | { source: "editor"; id: string; issue: ReviewIssue; reviewId: string };

export const coachNote = (issue: CoachIssue): Note => ({
  source: "coach",
  id: coachAnnotationId(issue),
  issue,
});

export const editorNote = (issue: ReviewIssue, reviewId: string): Note => ({
  source: "editor",
  id: editorAnnotationId(issue),
  issue,
  reviewId,
});

/** The block and words a note is about. */
export function noteAnchor(note: Note): { blockId: string; quote: string } {
  return note.source === "coach"
    ? { blockId: note.issue.block, quote: note.issue.excerpt }
    : { blockId: note.issue.block, quote: note.issue.quote };
}

/** The exact words that would replace the quote, if the note offers any. */
export function noteReplacement(note: Note): string | null {
  return note.source === "coach"
    ? note.issue.replacement
    : currentFix(note.issue).replacement;
}

/** Everything a note can have done to it. Cards call these; the workspace decides what they mean. */
export interface NoteActions {
  accept: (note: Note) => void;
  editHere: (note: Note) => void;
  dismiss: (note: Note) => void;
  resolve: (note: Note) => void;
  reopen: (note: Note) => void;
  discuss: (note: Note) => void;
  ignoreRule: (note: Note) => void;
  show: (note: Note) => void;
  openReference: (ref: string) => void;
}
