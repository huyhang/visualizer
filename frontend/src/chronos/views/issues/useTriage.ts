// Triage: work down the report one issue at a time. j/k (or the arrows) move,
// the chosen issue opens beside the list, and when a fix lands the report
// re-checks and triage stays where it was -- on the same issue if it is still
// wrong, on the next one if it is not, which opens in its turn. When nothing
// is left to walk, triage stops.

import { useCallback, useEffect, useRef, useState } from "react";
import type { Issue } from "../../api/types";
import { issueKey, keepPlace, step } from "../../logic/report";
import { topDialog } from "../../components/common/layers";

export interface Triage {
  on: boolean;
  index: number;
  current: Issue | null;
  start: () => void;
  stop: () => void;
  move: (delta: number) => void;
  choose: (index: number) => void;
}

/** Whether a key press belongs to a field the writer is typing in. */
export function typingIn(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || !el.tagName) return false;
  return /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable === true;
}

export function useTriage(order: Issue[], onSelect: (issue: Issue) => void): Triage {
  const [on, setOn] = useState(false);
  const [place, setPlace] = useState<{ key: string | null; index: number }>({
    key: null,
    index: -1,
  });
  const index = on ? keepPlace(order, place.key, place.index) : -1;
  const current = index >= 0 ? (order[index] ?? null) : null;
  // The issue last opened beside the list.
  const opened = useRef<string | null>(null);

  const choose = useCallback(
    (n: number) => {
      const issue = order[n];
      if (!issue) return;
      setOn(true);
      setPlace({ key: issueKey(issue), index: n });
      opened.current = issueKey(issue);
      onSelect(issue);
    },
    [order, onSelect],
  );
  const move = useCallback(
    (delta: number) => choose(step(index, delta, order.length)),
    [choose, index, order.length],
  );
  const start = useCallback(() => choose(Math.max(index, 0)), [choose, index]);
  const stop = useCallback(() => setOn(false), []);

  // A fix landed and the issue triage was on has gone: whatever took its place
  // is the one now chosen. With nothing left to walk, triage stops.
  const currentKey = current ? issueKey(current) : null;
  if (on && !current) setOn(false);
  else if (on && currentKey !== place.key) setPlace({ key: currentKey, index });

  // The chosen issue opens beside the list, once each time it changes.
  useEffect(() => {
    if (!on || !current || currentKey === opened.current) return;
    opened.current = currentKey;
    onSelect(current);
  }, [on, current, currentKey, onSelect]);

  useEffect(() => {
    if (!on) return;
    const onKey = (e: KeyboardEvent) => {
      if (typingIn(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      // An editor or menu over the list has the keys: a fix is being written there.
      if (e.defaultPrevented || topDialog()) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        move(1);
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        move(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [on, move]);

  return { on, index, current, start, stop, move, choose };
}
