// Autosave: every change is written to this device at once and to the server
// once typing pauses. Ported from the old writer's state machine, with its
// timer injected so a test drives time instead of waiting for it.
//
// The rule that matters: a newer snapshot always wins. A save that fails while
// the writer kept typing must never put its older words back over theirs.

export type SaveState = "local" | "saving" | "saved" | "offline" | "conflict" | "invalid";

export interface Timer {
  set: (run: () => void, ms: number) => unknown;
  clear: (handle: unknown) => void;
}

export const browserTimer: Timer = {
  set: (run, ms) => window.setTimeout(run, ms),
  clear: (handle) => window.clearTimeout(handle as number),
};

export interface AutosaveDeps<T> {
  saveLocal: (snapshot: T | null) => Promise<unknown> | unknown;
  saveRemote: (snapshot: T, urgent: boolean) => Promise<unknown>;
  onState: (state: SaveState, error?: unknown) => void;
  /** What a failed save means: someone else's newer copy, a refusal, or no network. */
  classify: (error: unknown) => "conflict" | "invalid" | "offline";
  timer?: Timer;
  delay?: number;
}

export interface Autosave<T> {
  schedule: (snapshot: T) => void;
  flush: (urgent?: boolean) => Promise<void>;
  hasPending: () => boolean;
}

export function createAutosave<T>({
  saveLocal,
  saveRemote,
  onState,
  classify,
  timer = browserTimer,
  delay = 900,
}: AutosaveDeps<T>): Autosave<T> {
  let handle: unknown = null;
  let pending: T | null = null;
  let saving = false;
  let active: Promise<void> | null = null;

  const later = () => {
    timer.clear(handle);
    handle = timer.set(() => void flush(false), delay);
  };

  const schedule = (snapshot: T) => {
    pending = snapshot;
    Promise.resolve(saveLocal(snapshot)).catch(() => {});
    onState("local");
    later();
  };

  const perform = async (urgent: boolean) => {
    const snapshot = pending as T;
    pending = null;
    saving = true;
    onState("saving");
    try {
      await saveRemote(snapshot, urgent);
      if (!pending) await Promise.resolve(saveLocal(null));
      onState("saved");
    } catch (error) {
      // A newer keystroke may have landed while this was in flight; its
      // snapshot subsumes this one and must not be replaced by it.
      if (!pending) pending = snapshot;
      onState(classify(error), error);
    } finally {
      saving = false;
      if (pending && pending !== snapshot && !urgent) later();
    }
  };

  async function flush(urgent = false): Promise<void> {
    timer.clear(handle);
    if (saving) {
      await active;
      if (urgent && pending) return flush(true);
      return;
    }
    if (!pending) return;
    active = perform(urgent);
    await active;
    active = null;
  }

  return { schedule, flush, hasPending: () => pending !== null };
}
