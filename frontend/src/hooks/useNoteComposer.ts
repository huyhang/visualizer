// The note side of the studio: the composition, opening an existing note into
// it, saving it, and the bridge the draft pane uses to add material.

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api/context";
import { ApiError, messageOf } from "../api/errors";
import type { NoteBridge } from "../components/draft/DraftPane";
import type { NotePaneProps } from "../components/note/NotePane";
import type { Notice } from "../components/ui/Toaster";
import * as compose from "../logic/compose";
import { plural, slugOf } from "../logic/format";
import { keys } from "./keys";
import { useComposition, type CompositionStore } from "./useComposition";
import type { StudioActions } from "./useStudioActions";

export function useNoteComposer({
  store,
  newId,
  save: saveMutation,
  notify,
  onOpening,
}: {
  store: CompositionStore;
  newId: compose.NewId;
  save: StudioActions["save"];
  notify: (notice: Notice) => void;
  onOpening: () => void;
}) {
  const api = useApi();
  const client = useQueryClient();
  const [comp, update] = useComposition(store);
  const [loadingNote, setLoadingNote] = useState(false);

  const bridge: NoteBridge = {
    addText: (text, from) => update((c) => compose.addText(c, text, from, newId)),
    hasText: (text) => compose.hasText(comp, text),
    addImage: (image) => update((c) => compose.addImage(c, image, newId)),
    hasImage: (from, index) => compose.hasImage(comp, from, index),
  };

  /** Open a note to add to. `prepare` trims the composition first (after a save). */
  async function openNote(
    slug: string,
    prepare: (c: compose.Composition) => compose.Composition = (c) => c,
  ) {
    setLoadingNote(true);
    onOpening();
    try {
      const found = await client.fetchQuery({
        queryKey: keys.note(slug),
        queryFn: () => api.getNote(slug),
        staleTime: 0,
      });
      const { title, body } = found.document;
      const note = {
        slug,
        rev: found.rev,
        title: typeof title === "string" ? title : slug,
        body: typeof body === "string" ? body : "",
      };
      update((c) => compose.onExisting(prepare(c), note, newId));
      saveMutation.reset();
    } catch (error) {
      notify({
        title: "Could not open the note",
        description: messageOf(error),
        tone: "danger",
      });
    } finally {
      setLoadingNote(false);
    }
  }

  async function save() {
    try {
      const title = comp.title.trim();
      // Only what was saved leaves the composer: anything added while the save
      // and the reload were under way stays.
      const sent = new Set(comp.blocks.map((b) => b.id));
      const saved = await saveMutation.mutateAsync({
        comp,
        // Onto the note as it is now, not as it was sent: what was added
        // meanwhile stays.
        onImported: (media) => update((c) => compose.withMedia(c, media)),
      });
      const slug = slugOf(saved.note);
      const cited = saved.sources.length + saved.relinked.length;
      notify({
        title: `Saved “${title}”`,
        description: cited
          ? `${plural(cited, "source")} cited from your world's sources.`
          : undefined,
        action: {
          label: "Open",
          href: api.articleUrl({ db: api.world, col: "research", id: slug }),
        },
      });
      // Keep writing into the note just saved, as it now stands.
      await openNote(slug, (c) => compose.withoutBlocks(c, sent));
    } catch {
      /* shown in the save bar */
    }
  }

  const error = saveMutation.error;
  const activeNote = comp.target.kind === "existing" ? comp.target.slug : null;

  const paneProps: Omit<NotePaneProps, "notes" | "linkTo"> = {
    comp,
    loadingNote,
    saving: saveMutation.isPending,
    saveError: error
      ? {
          message: messageOf(error),
          conflict: error instanceof ApiError && error.isConflict,
        }
      : null,
    onTitle: (title) => update((c) => compose.setTitle(c, title)),
    onNew: () => {
      update(compose.onNew);
      saveMutation.reset();
    },
    onExisting: (slug) => void openNote(slug),
    onAddOwn: () => {
      const { comp: next, id } = compose.addBlank(comp, newId);
      update(() => next);
      return id;
    },
    onChange: (id, patch) => update((c) => compose.updateBlock(c, id, patch)),
    onMove: (id, delta) => update((c) => compose.moveBlock(c, id, delta)),
    onRemove: (id) => update((c) => compose.removeBlock(c, id)),
    onClear: () => {
      update(() => compose.emptyComposition());
      saveMutation.reset();
    },
    onSave: () => void save(),
    onReload: () => activeNote && void openNote(activeNote),
  };

  return { comp, bridge, activeNote, openNote, paneProps };
}
