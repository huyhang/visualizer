// Where each row's line actually sits, measured.
//
// The classic map positioned rows at computed heights and chased the browser
// with a measure-and-redraw loop, because a row's real height depends on the
// window, the reader's text size and how its goal marks wrap. Here the rows
// flow like any list and the drawing follows them instead: every row marks its
// line with `data-anchor`, this measures those, and the dots and curves are
// drawn at the measured heights. Nothing can overlap, at any text size.

import { useLayoutEffect, useState, type RefObject } from "react";

export interface Anchors {
  /** Slot id -> the y of its line, relative to the rows' container. */
  centres: Map<string, number>;
  height: number;
}

function same(a: Anchors | null, b: Anchors): boolean {
  if (!a || a.height !== b.height || a.centres.size !== b.centres.size) return false;
  for (const [id, y] of b.centres) if (a.centres.get(id) !== y) return false;
  return true;
}

/** Measure the anchors under `container`; null until something with height is on screen. */
export function measureAnchors(container: HTMLElement): Anchors | null {
  const box = container.getBoundingClientRect();
  if (!box.height) return null;
  const centres = new Map<string, number>();
  container.querySelectorAll<HTMLElement>("[data-anchor]").forEach((el) => {
    const r = el.getBoundingClientRect();
    centres.set(el.dataset.anchor ?? "", Math.round(r.top - box.top + r.height / 2));
  });
  return { centres, height: Math.ceil(box.height) };
}

export function useAnchors(
  container: RefObject<HTMLElement | null>,
  version: unknown,
): Anchors | null {
  const [anchors, setAnchors] = useState<Anchors | null>(null);
  useLayoutEffect(() => {
    const el = container.current;
    if (!el) return;
    const measure = () => {
      const next = measureAnchors(el);
      setAnchors((prev) => (next === null ? null : same(prev, next) ? prev : next));
    };
    measure();
    // The container changes size whenever a row opens, a mark wraps or the
    // text size changes -- every reason a line can move.
    const observer =
      typeof ResizeObserver === "function" ? new ResizeObserver(measure) : null;
    observer?.observe(el);
    return () => observer?.disconnect();
  }, [container, version]);
  return anchors;
}
