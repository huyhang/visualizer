import type { HashLocation, KeyValueStore } from "../deps";

/** A `KeyValueStore` that forgets when the test ends. */
export function memoryStore(seed: Record<string, string> = {}): KeyValueStore & {
  data: Record<string, string>;
} {
  const data = { ...seed };
  return {
    data,
    get: (key) => (key in data ? (data[key] ?? null) : null),
    set: (key, value) => {
      data[key] = value;
    },
  };
}

/** An address bar that only exists in memory, with its history. */
export function memoryLocation(initial = "#/"): HashLocation & { history: string[] } {
  let hash = initial;
  const history = [initial];
  const listeners = new Set<() => void>();
  const change = (next: string, push: boolean) => {
    hash = next;
    if (push) history.push(next);
    else history[history.length - 1] = next;
    listeners.forEach((l) => l());
  };
  return {
    history,
    current: () => hash,
    push: (next) => change(next, true),
    replace: (next) => change(next, false),
    subscribe: (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
  };
}
