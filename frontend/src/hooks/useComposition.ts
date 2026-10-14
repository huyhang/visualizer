// The note being composed, kept in this browser so a reload -- or a trip to
// the article editor and back -- does not lose it. Storage and id generation
// are injected; the defaults are the browser's.

import { useCallback, useEffect, useState } from "react";
import { emptyComposition, type Composition, type NewId } from "../logic/compose";

export interface CompositionStore {
  load(): Composition | null;
  save(comp: Composition): void;
}

export function localStore(
  world: string,
  storage: Storage | null = safeStorage(),
): CompositionStore {
  const key = `akasha-studio-note:${world}`;
  return {
    load() {
      try {
        const raw = storage?.getItem(key);
        const parsed = raw ? (JSON.parse(raw) as Composition) : null;
        return parsed && Array.isArray(parsed.blocks) && parsed.target ? parsed : null;
      } catch {
        return null;
      }
    },
    save(comp) {
      try {
        storage?.setItem(key, JSON.stringify(comp));
      } catch {
        /* private mode, or full: the note simply is not remembered */
      }
    },
  };
}

function safeStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

let counter = 0;
export const browserId: NewId = () =>
  globalThis.crypto?.randomUUID?.() ??
  `b${Date.now().toString(36)}${(counter++).toString(36)}`;

export function useComposition(store: CompositionStore) {
  const [comp, setComp] = useState<Composition>(() => store.load() ?? emptyComposition());
  useEffect(() => store.save(comp), [store, comp]);
  const update = useCallback(
    (change: (comp: Composition) => Composition) => setComp(change),
    [],
  );
  return [comp, update] as const;
}
