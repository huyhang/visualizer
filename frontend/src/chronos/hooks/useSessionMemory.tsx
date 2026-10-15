// What a screen remembers for the rest of the visit -- the thread table's
// filter and page, say -- so coming back to it lands where the writer left.
// Held by the app rather than in a module, so two workspaces (or two tests)
// never share a memory, and forgotten when the tab closes, as the classic page did.

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

const MemoryContext = createContext<Map<string, unknown> | null>(null);

export function SessionMemoryProvider({ children }: { children: ReactNode }) {
  const [memory] = useState(() => new Map<string, unknown>());
  return <MemoryContext.Provider value={memory}>{children}</MemoryContext.Provider>;
}

/** Like `useState`, but what it holds outlives the screen for the rest of the visit. */
export function useSessionMemory<T>(key: string, initial: T): [T, (next: T) => void] {
  const memory = useContext(MemoryContext);
  if (!memory)
    throw new Error("useSessionMemory() needs a <SessionMemoryProvider> above it.");
  const [value, setValue] = useState<T>(() =>
    memory.has(key) ? (memory.get(key) as T) : initial,
  );
  const remember = useCallback(
    (next: T) => {
      memory.set(key, next);
      setValue(next);
    },
    [memory, key],
  );
  return [value, remember];
}
