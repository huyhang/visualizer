// Durable local recovery plus a small, injected autosave state machine.

export const recoveryKey = ({ user, book, volume, section, draft }) =>
  [user, book, volume, section, draft].map(encodeURIComponent).join("/");

export function createRecoveryStore(factory = globalThis.indexedDB) {
  const open = () => new Promise((resolve, reject) => {
    if (!factory) { resolve(null); return; }
    const request = factory.open("logos-writing", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("drafts");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const transact = async (mode, action) => {
    const database = await open();
    if (!database) return null;
    return new Promise((resolve, reject) => {
      const transaction = database.transaction("drafts", mode);
      const request = action(transaction.objectStore("drafts"));
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
      transaction.oncomplete = () => database.close();
    });
  };
  return {
    get: (key) => transact("readonly", (store) => store.get(key)),
    set: (key, value) => transact("readwrite", (store) => store.put(value, key)),
    remove: (key) => transact("readwrite", (store) => store.delete(key)),
  };
}

export function createAutosave({ saveLocal, saveRemote, onState, delay = 900 }) {
  let timer = null;
  let pending = null;
  let saving = false;
  let active = null;

  const schedule = (snapshot) => {
    pending = snapshot;
    Promise.resolve(saveLocal(snapshot)).catch(() => {});
    onState("local");
    clearTimeout(timer);
    timer = setTimeout(() => flush(false), delay);
  };

  const perform = async (urgent) => {
    const snapshot = pending;
    pending = null;
    saving = true;
    onState("saving");
    try {
      await saveRemote(snapshot, urgent);
      if (!pending) await Promise.resolve(saveLocal(null));
      onState("saved");
    } catch (error) {
      // A newer keystroke may have arrived while this request was in flight.
      // Its snapshot subsumes this one and must never be replaced by the older
      // failed payload.
      if (!pending) pending = snapshot;
      const state = error && error.status === 409 ? "conflict"
        : error && error.status >= 400 && error.status < 500 ? "invalid" : "offline";
      onState(state, error);
    } finally {
      saving = false;
      if (pending && pending !== snapshot && !urgent) {
        clearTimeout(timer);
        timer = setTimeout(() => flush(false), delay);
      }
    }
  };

  const flush = async (urgent = false) => {
    clearTimeout(timer);
    if (saving) {
      await active;
      if (urgent && pending) return flush(true);
      return;
    }
    if (!pending) return;
    active = perform(urgent);
    await active;
    active = null;
  };

  return { schedule, flush, hasPending: () => Boolean(pending) };
}
