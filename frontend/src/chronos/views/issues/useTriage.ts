// Triage: work down the report one issue at a time. j/k (or the arrows) move,
// the chosen issue opens beside the list, and when a fix lands the report
// re-checks and triage stays where it was -- on the same issue if it is still
// wrong, on the next one if it is not.

import { useCallback, useEffect, useState } from "react";
import type { Issue } from "../../api/types";
import { issueKey, keepPlace, step } from "../../logic/report";

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

  const choose = useCallback(
    (n: number) => {
      const issue = order[n];
      if (!issue) return;
      setOn(true);
      setPlace({ key: issueKey(issue), index: n });
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

  useEffect(() => {
    if (!on) return;
    const onKey = (e: KeyboardEvent) => {
      if (typingIn(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
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
