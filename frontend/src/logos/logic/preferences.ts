// What the writer chose and this browser remembers, per account. The dialect
// and the ignored Coach rules use the old writer's keys, which the reader's
// series Review page reads too, so both pages keep agreeing.

import type { Check, Dialect, VerifyMode } from "../api/types";

export interface KeyValueStore {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

export interface ReviewOptions {
  checks: Check[];
  verify: VerifyMode;
}

export interface Layers {
  coach: boolean;
  editor: boolean;
}

export interface Preferences {
  dialect: () => Dialect;
  setDialect: (dialect: Dialect) => void;
  ignoredRules: () => string[];
  ignoreRule: (title: string) => void;
  reviewOptions: () => ReviewOptions;
  setReviewOptions: (options: ReviewOptions) => void;
  layers: () => Layers;
  setLayers: (layers: Layers) => void;
}

const DEFAULT_OPTIONS: ReviewOptions = {
  checks: ["continuity", "anachronism", "prose"],
  verify: "auto",
};

function read<T>(
  store: KeyValueStore,
  key: string,
  fallback: T,
  valid: (value: unknown) => boolean,
): T {
  try {
    const raw = store.getItem(key);
    if (raw === null) return fallback;
    const value = JSON.parse(raw);
    return valid(value) ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(store: KeyValueStore, key: string, value: unknown) {
  try {
    store.setItem(key, typeof value === "string" ? value : JSON.stringify(value));
  } catch {
    // Private browsing and full storage: the choice still applies to this page.
  }
}

export function storedPreferences(store: KeyValueStore, user: string): Preferences {
  const who = encodeURIComponent(user);
  const keys = {
    dialect: `logos-writing-dialect:${who}`,
    ignored: `logos-writing-ignored:${who}`,
    review: `logos-review-options:${who}`,
    layers: `logos-writing-layers:${who}`,
  };
  return {
    dialect: () => {
      try {
        return store.getItem(keys.dialect) === "en-GB" ? "en-GB" : "en-US";
      } catch {
        return "en-US";
      }
    },
    setDialect: (dialect) => write(store, keys.dialect, dialect),
    ignoredRules: () => read<string[]>(store, keys.ignored, [], Array.isArray),
    ignoreRule: (title) => {
      const ignored = new Set(read<string[]>(store, keys.ignored, [], Array.isArray));
      ignored.add(title);
      write(store, keys.ignored, [...ignored]);
    },
    reviewOptions: () =>
      read(store, keys.review, DEFAULT_OPTIONS, (value) => {
        const v = value as ReviewOptions;
        return (
          Array.isArray(v?.checks) &&
          v.checks.length > 0 &&
          ["auto", "required", "off"].includes(v.verify)
        );
      }),
    setReviewOptions: (options) => write(store, keys.review, options),
    layers: () =>
      read<Layers>(store, keys.layers, { coach: true, editor: true }, (value) => {
        const v = value as Layers;
        return typeof v?.coach === "boolean" && typeof v?.editor === "boolean";
      }),
    setLayers: (layers) => write(store, keys.layers, layers),
  };
}

/** A store that forgets on reload, for tests. */
export function memoryStore(seed: Record<string, string> = {}): KeyValueStore {
  const held = new Map(Object.entries(seed));
  return {
    getItem: (key) => held.get(key) ?? null,
    setItem: (key, value) => void held.set(key, value),
  };
}
