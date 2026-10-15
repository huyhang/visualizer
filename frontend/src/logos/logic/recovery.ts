// The copy of unsaved words kept on this device, so a closed tab, a crash or a
// dropped connection loses nothing. Same database, store and record shape as
// the old writer kept, so a copy it left behind is still found.

import type { LogosDocument } from "../doc/types";
import type { Caret } from "../editor/positions";

export interface RecoverySnapshot {
  document: LogosDocument;
  name: string;
  title: string;
  /** The draft revision these words were typed over. */
  draftRev: number;
  caret: Caret | null;
  savedAt: string;
}

export interface RecoveryStore {
  get: (key: string) => Promise<RecoverySnapshot | null>;
  set: (key: string, value: RecoverySnapshot) => Promise<unknown>;
  remove: (key: string) => Promise<unknown>;
}

export interface RecoveryPlace {
  user: string;
  book: string;
  volume: string;
  section: string;
  draft: string;
}

/** One copy per account and draft: two writers on one browser never see each other's. */
export const recoveryKey = ({ user, book, volume, section, draft }: RecoveryPlace) =>
  [user, book, volume, section, draft].map(encodeURIComponent).join("/");

export function indexedDbRecovery(
  factory: IDBFactory | undefined = globalThis.indexedDB,
): RecoveryStore {
  const open = () =>
    new Promise<IDBDatabase | null>((resolve, reject) => {
      if (!factory) return resolve(null);
      const request = factory.open("logos-writing", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("drafts");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  const transact = async <T>(
    mode: IDBTransactionMode,
    action: (store: IDBObjectStore) => IDBRequest,
  ) => {
    const database = await open();
    if (!database) return null;
    return new Promise<T | null>((resolve, reject) => {
      const transaction = database.transaction("drafts", mode);
      const request = action(transaction.objectStore("drafts"));
      request.onsuccess = () => resolve((request.result as T) ?? null);
      request.onerror = () => reject(request.error);
      transaction.oncomplete = () => database.close();
    });
  };
  return {
    get: (key) => transact<RecoverySnapshot>("readonly", (store) => store.get(key)),
    set: (key, value) => transact("readwrite", (store) => store.put(value, key)),
    remove: (key) => transact("readwrite", (store) => store.delete(key)),
  };
}

/** A store that lives as long as the page: for tests, and browsers without IndexedDB. */
export function memoryRecovery(seed: Record<string, RecoverySnapshot> = {}): RecoveryStore {
  const held = new Map(Object.entries(seed));
  return {
    get: async (key) => held.get(key) ?? null,
    set: async (key, value) => held.set(key, value),
    remove: async (key) => held.delete(key),
  };
}
