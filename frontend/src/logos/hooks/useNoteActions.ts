// What each note action means, for either kind of note. Accepting rewrites the
// quoted words -- the ones underlined, where the same words come twice -- as
// one undoable edit and marks the issue resolved; dismissing sets it aside;
// both offer Undo, which puts back exactly what was there. An editor's issue is
// triaged on the server; a Coach finding only for this visit, as the Coach
// always worked.

import type { Editor } from "@tiptap/core";
import { useMemo } from "react";
import type { IssueStatus, ReviewIssue } from "../api/types";
import { useNotify } from "../../components/ui/Toaster";
import { useDeps } from "../deps";
import { annotationState } from "../editor/annotations";
import { parseRef } from "../logic/refs";
import { noteAnchor, noteReplacement, type Note, type NoteActions } from "../logic/notes";
import type { Coach } from "./useCoach";
import type { EditorReview } from "./useEditorReview";

export interface NoteHost {
  editor: Editor;
  review: EditorReview;
  coach: Coach;
  /** The issue as it is now, for an Undo pressed after it has changed. */
  issueNow: (id: string) => ReviewIssue | undefined;
  /** Open an issue in full in the Editor tab. */
  openIssue: (id: string) => void;
  /** Put the caret and the writer's eyes on the note's words. */
  reveal: (note: Note) => void;
  /** The popover is done with. */
  closeNote: () => void;
  /** Leave a drawer, so the prose is what the writer sees. */
  toProse: () => void;
}

export function useNoteActions(host: NoteHost): NoteActions {
  const { api, openTab } = useDeps();
  const notify = useNotify();

  return useMemo(() => {
    const status = (note: Note, value: IssueStatus) => {
      if (note.source !== "editor") return;
      const issue = host.issueNow(note.issue.id) ?? note.issue;
      host.review.setStatus.mutate(
        { reviewId: note.reviewId, issue, status: value },
        {
          onError: () =>
            notify({
              title: "That did not save",
              description: "The issue is as it was.",
              tone: "danger",
            }),
        },
      );
    };

    const setAside = (note: Note, value: "dismissed" | "resolved") => {
      if (note.source === "coach") host.coach.dismiss(note.issue.id);
      else status(note, value);
    };

    const putBack = (note: Note) => {
      if (note.source === "coach") host.coach.restore(note.issue.id);
      else status(note, "open");
    };

    /** Where the note's words are underlined now, if they are. */
    const underlined = (note: Note) =>
      annotationState(host.editor.state)?.placement[note.id] ?? null;

    return {
      accept: (note) => {
        const { blockId, quote } = noteAnchor(note);
        const replacement = noteReplacement(note);
        if (!replacement) return;
        const fix = { blockId, quote, replacement, at: underlined(note), track: note.id };
        if (!host.editor.commands.applyFix(fix)) {
          notify({
            title: "Those words have changed",
            description: "Edit the passage yourself, or mark the note resolved.",
            tone: "danger",
          });
          return;
        }
        host.closeNote();
        setAside(note, "resolved");
        notify({
          title: "Fix applied",
          description: `“${replacement.length > 60 ? `${replacement.slice(0, 57)}…` : replacement}”`,
          action: {
            label: "Undo",
            onClick: () => {
              if (!host.editor.commands.revertFix(note.id)) {
                notify({
                  title: "The words were left as they are",
                  description: "They have changed since the fix. The note is open again.",
                });
              }
              putBack(note);
            },
          },
        });
      },
      editHere: (note) => {
        const { blockId, quote } = noteAnchor(note);
        host.closeNote();
        host.toProse();
        host.editor.chain().focus().selectQuote(blockId, quote, underlined(note)).run();
      },
      dismiss: (note) => {
        host.closeNote();
        setAside(note, "dismissed");
        notify({
          title: "Dismissed",
          action: { label: "Undo", onClick: () => putBack(note) },
        });
      },
      resolve: (note) => {
        host.closeNote();
        setAside(note, "resolved");
      },
      reopen: (note) => putBack(note),
      discuss: (note) => {
        if (note.source !== "editor") return;
        host.closeNote();
        host.openIssue(note.issue.id);
      },
      ignoreRule: (note) => {
        if (note.source !== "coach") return;
        host.closeNote();
        host.coach.ignoreRule(note.issue.title);
        notify({
          title: `“${note.issue.title}” is ignored`,
          description: "The Coach won’t raise it again.",
        });
      },
      show: (note) => host.reveal(note),
      openReference: (ref) => {
        const parsed = parseRef(ref);
        if (parsed) openTab(api.articleUrl(parsed));
      },
    };
  }, [api, host, notify, openTab]);
}
