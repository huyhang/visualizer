import { useLayoutEffect, useRef } from "react";

/**
 * A ref that always holds the latest `value`. For callbacks handed to code that
 * outlives a render -- the editor's plugins, autosave, timers -- so they call
 * today's function rather than the one from the first render.
 */
export function useLatest<T>(value: T) {
  const ref = useRef(value);
  useLayoutEffect(() => {
    ref.current = value;
  });
  return ref;
}
