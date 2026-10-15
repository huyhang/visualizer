// Everything the workspace depends on that is not React: the API, the address
// bar, what the browser remembers and where the other services live.
// `main.tsx` builds the real ones; tests build fakes. Nothing below the
// provider reaches for a browser global for any of these.

import { createContext, useContext, type ReactNode } from "react";
import type { ChronosApi } from "./api/ChronosApi";

/** The address bar's hash, as the router reads and writes it. */
export interface HashLocation {
  current: () => string;
  /** Go somewhere new: Back returns here. */
  push: (hash: string) => void;
  /** Say the same place differently: Back skips it. */
  replace: (hash: string) => void;
  subscribe: (onChange: () => void) => () => void;
}

/** A string store for preferences that outlive the tab. */
export interface KeyValueStore {
  get: (key: string) => string | null;
  set: (key: string, value: string) => void;
}

export interface ChronosDeps {
  api: ChronosApi;
  location: HashLocation;
  store: KeyValueStore;
  user: string;
  /** Where Akasha's article editor is, for "open the article". */
  akashaUrl: string;
  /** The classic visualiser at the same place, for anyone who wants it back. */
  classicUrl: (hash: string) => string;
  /** The session has gone: send the writer to sign in again. */
  signIn: () => void;
}

const DepsContext = createContext<ChronosDeps | null>(null);

export function ChronosDepsProvider({
  deps,
  children,
}: {
  deps: ChronosDeps;
  children: ReactNode;
}) {
  return <DepsContext.Provider value={deps}>{children}</DepsContext.Provider>;
}

export function useDeps(): ChronosDeps {
  const deps = useContext(DepsContext);
  if (!deps) throw new Error("useDeps() needs a <ChronosDepsProvider> above it.");
  return deps;
}

export function useApi(): ChronosApi {
  return useDeps().api;
}

/** The window's own hash. */
export function windowLocation(win: Window): HashLocation {
  return {
    current: () => win.location.hash,
    push: (hash) => {
      win.location.hash = hash;
    },
    replace: (hash) => {
      const { pathname, search } = win.location;
      win.history.replaceState(win.history.state, "", pathname + search + hash);
      win.dispatchEvent(new HashChangeEvent("hashchange"));
    },
    subscribe: (onChange) => {
      win.addEventListener("hashchange", onChange);
      return () => win.removeEventListener("hashchange", onChange);
    },
  };
}

/** `localStorage`, forgiving a browser that refuses it (private mode, quota). */
export function browserStore(storage: Storage): KeyValueStore {
  return {
    get: (key) => {
      try {
        return storage.getItem(key);
      } catch {
        return null;
      }
    },
    set: (key, value) => {
      try {
        storage.setItem(key, value);
      } catch {
        // Remembering is a courtesy; failing to is not worth interrupting anyone.
      }
    },
  };
}
