// Saving a composed note: import the images it shows, then save the note.
//
// A plain function over the injected api, so the order of calls can be tested
// without React. Images are imported first because a note must name each by
// its media id. `onImported` hands back the ids imported (block id -> media
// id), even when a later import fails, so the composer can record them on the
// note as it now stands -- including anything added while this ran -- and a
// retried save does not import the same pictures again.

import { ApiError, messageOf } from "../api/errors";
import type { ResearchApi } from "../api/ResearchApi";
import type { NoteSaved } from "../api/types";
import {
  noteRequest,
  pendingImages,
  withMedia,
  type Composition,
  type ImageBlock,
} from "../logic/compose";

export async function saveComposition(
  api: ResearchApi,
  comp: Composition,
  onImported: (media: ReadonlyMap<string, string>) => void,
): Promise<NoteSaved> {
  const media = new Map<string, string>();
  try {
    for (const block of pendingImages(comp)) {
      media.set(block.id, await importImage(api, block));
    }
  } finally {
    if (media.size) onImported(media);
  }
  return api.saveNote(noteRequest(withMedia(comp, media)));
}

/** One image into the world's library, or an error that says which image. */
async function importImage(api: ResearchApi, block: ImageBlock): Promise<string> {
  try {
    return (await api.importImage(block.draft, block.index)).id;
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    throw new ApiError(
      status,
      `The picture “${block.caption || "untitled"}” could not be imported ` +
        `(${messageOf(error)}). Remove it from the note and save again.`,
    );
  }
}
