// One open draft, kept safe -- as a plain store, apart from React, so every
// rule here is tested without rendering anything.
//
// Autosave writes to this device at once and to the server when typing
// pauses, the section's title with it. Each draft action -- rename, new draft,
// make primary, switch, leave -- waits for the words in flight first, so
// nothing navigates, clones or promotes on top of them. A save another tab
// beat is never overwritten: it becomes a conflict the writer can preserve as
// a new draft.

import type { LogosApi, SectionAddress } from "../api/LogosApi";
import { saveFailure } from "../api/errors";
import type { Draft, DraftListing, Manuscript, Section } from "../api/types";
import type { LogosDocument } from "../doc/types";
import type { Caret } from "../editor/positions";
import { createAutosave, type SaveState, type Timer } from "./autosave";
import { promoted, renamed, saved, sectionChanged, type DraftState } from "./drafts";
import { allSectionIds, availableId } from "./outline";
import { recoveryKey, type RecoverySnapshot, type RecoveryStore } from "./recovery";

/** How the page reads the editor it does not own. */
export interface EditorReader {
  document: () => LogosDocument;
  caret: () => Caret | null;
}

export interface SaveStatus {
  state: SaveState;
  message?: string;
}

export interface SessionState {
  drafts: DraftState;
  title: string;
  status: SaveStatus;
}

export interface SessionInput {
  manuscript: Manuscript;
  at: SectionAddress;
  section: Section;
  listing: DraftListing;
  draft: Draft;
  recovered: RecoverySnapshot | null;
}

export interface SessionDeps {
  api: LogosApi;
  recovery: RecoveryStore;
  timer: Timer;
  navigate: (url: string) => void;
  user: string;
  reader: EditorReader;
  now?: () => Date;
}

export function createDraftSession(input: SessionInput, deps: SessionDeps) {
  const { api, recovery, timer, navigate, user, reader, now = () => new Date() } = deps;
  const { at, manuscript, section, listing, draft, recovered } = input;
  const key = recoveryKey({ user, ...at, draft: draft.id });

  let state: SessionState = {
    drafts: { rows: listing.drafts, current: draft, sectionRev: listing.section_rev },
    title: recovered?.title || section.title || "",
    status: { state: "saved" },
  };
  let sectionTitle = section.title ?? "";
  const listeners = new Set<() => void>();
  const set = (patch: Partial<SessionState>) => {
    state = { ...state, ...patch };
    for (const listener of listeners) listener();
  };
  const update = (change: (drafts: DraftState) => DraftState) =>
    set({ drafts: change(state.drafts) });

  const autosave = createAutosave<RecoverySnapshot>({
    timer,
    classify: saveFailure,
    saveLocal: (snapshot) =>
      snapshot ? recovery.set(key, snapshot) : recovery.remove(key),
    saveRemote: async (snapshot, urgent) => {
      const current = state.drafts.current;
      const record = await api.saveDraft(
        at,
        current.id,
        { name: snapshot.name, document: snapshot.document },
        current.rev,
        urgent,
      );
      update((drafts) => saved(drafts, record));
      if (snapshot.title !== sectionTitle) {
        const moved = await api.updateSectionTitle(
          at,
          snapshot.title || null,
          state.drafts.sectionRev,
        );
        sectionTitle = moved.title ?? "";
        update((drafts) => sectionChanged(drafts, moved.rev));
      }
    },
    onState: (saveState, error) =>
      set({
        status: {
          state: saveState,
          message: error instanceof Error ? error.message : undefined,
        },
      }),
  });

  const snapshot = (): RecoverySnapshot => ({
    document: reader.document(),
    name: state.drafts.current.name,
    title: state.title.trim(),
    draftRev: state.drafts.current.rev,
    caret: reader.caret(),
    savedAt: now().toISOString(),
  });

  const changed = () => autosave.schedule(snapshot());

  /** Wait for the words in flight; false if some could not be saved. */
  const settled = async (urgent = false) => {
    await autosave.flush(urgent);
    return !autosave.hasPending();
  };

  const leave = async (url: string) => {
    if (await settled(true)) navigate(url);
  };

  const actions = {
    saveNow: () => void autosave.flush(false),
    flushUrgently: () => void autosave.flush(true),
    settled,
    leave,
    switchDraft: (id: string) => leave(api.writerUrl(at, id)),
    rename: (name: string) => {
      update((drafts) => renamed(drafts, name));
      changed();
    },
    newDraft: async (name: string) => {
      if (!(await settled())) return;
      const created = await api.createDraft(at, name, state.drafts.current.id);
      navigate(api.writerUrl(at, created.id));
    },
    makePrimary: async () => {
      if (!(await settled()) || state.drafts.current.primary) return;
      const result = await api.makePrimary(
        at,
        state.drafts.current.id,
        state.drafts.sectionRev,
      );
      update((drafts) => promoted(drafts, result.section_rev));
    },
    preserveConflict: async () => {
      const held = snapshot();
      const created = await api.createDraft(
        at,
        `Recovered ${now().toLocaleString()}`,
        state.drafts.current.id,
      );
      const kept = await api.saveDraft(
        at,
        created.id,
        { name: created.name, document: held.document },
        created.rev,
      );
      await recovery.remove(key).catch(() => {});
      navigate(api.writerUrl(at, kept.id));
    },
    createChapter: async (volume: string, title: string) => {
      if (!(await settled())) return;
      const id = availableId(title, allSectionIds(manuscript), "chapter");
      await api.createSection(at.book, volume, id, { kind: "chapter", title });
      navigate(api.writerUrl({ book: at.book, volume, section: id }));
    },
    done: async () => {
      const block = reader.caret()?.block ?? reader.document().content[0]?.id ?? null;
      await leave(api.readerUrl(at, block, state.drafts.current.id));
    },
  };

  return {
    getState: () => state,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    changed,
    setTitle: (title: string) => {
      set({ title });
      changed();
    },
    /**
     * Words this device kept: carry on saving them if they were typed over the
     * draft the server still has, else hold them as a conflict to preserve.
     */
    resume: () => {
      if (!recovered) return;
      if (recovered.draftRev === draft.rev) autosave.schedule(recovered);
      else set({ status: { state: "conflict" } });
    },
    actions,
  };
}

export type DraftSession = ReturnType<typeof createDraftSession>;
