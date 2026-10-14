// Which topic is open, kept in the URL's hash (#topic=rj_…) so a reload, or a
// link pasted to yourself, opens the same one.

import { useCallback, useSyncExternalStore } from "react";

const PREFIX = "#topic=";

function subscribe(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

export function topicFromHash(hash: string): string | null {
  return hash.startsWith(PREFIX)
    ? decodeURIComponent(hash.slice(PREFIX.length)) || null
    : null;
}

export function useSelection() {
  const selected = useSyncExternalStore(subscribe, () =>
    topicFromHash(window.location.hash),
  );
  const select = useCallback((id: string | null) => {
    const hash = id ? `${PREFIX}${encodeURIComponent(id)}` : "";
    if (window.location.hash !== hash) window.location.hash = hash;
  }, []);
  return [selected, select] as const;
}
