// A set of ids the writer opens and closes: scenes shown in full, stretches
// unfolded, moments hidden, goal marks revealed. Remembered for the rest of the
// visit under `key`, so it survives a change of selection -- ticking a thread
// on never shuts the scene you were reading -- and a trip away from the map.

import { useSessionMemory } from "../../hooks/useSessionMemory";
import { toggled } from "../../logic/map/selection";

export interface ToggleSet {
  ids: Set<string>;
  has: (id: string) => boolean;
  toggle: (id: string) => void;
  set: (ids: Iterable<string>) => void;
}

export function useToggleSet(key: string): ToggleSet {
  const [ids, setIds] = useSessionMemory<Set<string>>(key, new Set());
  return {
    ids,
    has: (id) => ids.has(id),
    toggle: (id) => setIds(toggled(ids, id)),
    set: (next) => setIds(new Set(next)),
  };
}
